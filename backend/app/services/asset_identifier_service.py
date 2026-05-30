# Location: backend/app/services/asset_identifier_service.py
#
# PURPOSE:
#   Given a user problem + domain, fetch relevant assets from ALL dynamic tables,
#   then ask Claude to generate the minimum questions needed to pinpoint ONE asset.
#
#   Questions are based on REAL column values from the actual asset rows:
#     "Which database? (Oracle / MySQL / PostgreSQL)"
#     "Which server? (jenkins-prod-01 / jenkins-prod-02)"
#     "Which region? (ap-south-1 / asia-southeast1)"
#
#   After each answer, search all tables for a matching row.
#   If exactly 1 row found → confident match → route to owner.
#   If 0 rows found → relax filters → best-effort match → domain fallback.

import json
import re
from typing import Optional, List, Dict
from sqlalchemy.orm import Session
from sqlalchemy import text
import anthropic

from app.core.config import settings

_client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — FETCH CANDIDATE ASSETS FROM DB
# ─────────────────────────────────────────────────────────────────────────────

# Domain → keywords to search in asset data
DOMAIN_KEYWORDS = {
    "networking":          ["router", "switch", "firewall", "vpn", "network", "dns", "proxy", "load balancer"],
    "security":            ["firewall", "waf", "ids", "siem", "dlp", "nessus", "security"],
    "database":            ["oracle", "mysql", "postgres", "mongodb", "redis", "cassandra", "elasticsearch", "database", "db"],
    "devops":              ["jenkins", "gitlab", "kubernetes", "k8s", "nexus", "sonar", "ci", "pipeline", "deployment", "deploy"],
    "software":            ["app", "api", "microservice", "portal", "gateway", "payment", "service", "checkout", "ecommerce", "web"],
    "cloud":               ["ec2", "gcp", "azure", "s3", "cloud", "vm", "instance", "bucket", "payment", "ecommerce", "portal", "api", "web", "sap", "batch"],
    "infrastructure":      ["hypervisor", "vcenter", "esxi", "backup", "storage", "monitoring"],
    "hardware":            ["blade", "server", "workstation", "printer"],
    "email_communication": ["exchange", "smtp", "mail", "teams", "slack", "email"],
    "erp_business_apps":   ["sap", "oracle ebs", "salesforce", "servicenow", "erp", "crm"],
    "identity_access":     ["ldap", "active directory", "sso", "pam", "radius", "login", "auth", "password", "access"],
    "endpoint_management": ["mdm", "antivirus", "patch", "endpoint", "laptop", "desktop", "device"],
    # Generic fallback keywords — used when domain is "other"
    "other":               ["payment", "checkout", "purchase", "order", "invoice", "service", "system", "application"],
}

# Columns whose values make good question options (not emails, not IPs)
GOOD_QUESTION_ROLES = {"identifier", "environment", "region", "application", "team", "os", "power_state", "other"}
SKIP_ROLES          = {"contact_email", "manager_email", "director_email", "ops_email", "ip"}


def fetch_assets(db: Session, domain: str, problem: str, limit: int = 40) -> tuple[list, list]:
    """
    Fetch candidate asset rows from ALL dynamic tables.
    Returns: (rows_list, tables_meta_list)
      rows_list: list of dicts, each row has all column values + _table_name
      tables_meta: list of {table_name, display_name, columns_meta}
    """
    from app.services.dynamic_table_service import get_all_tables
    from app.core.database import SessionLocal

    fresh_db = SessionLocal()
    try:
        tables   = get_all_tables(fresh_db)
        all_rows = []
        meta     = []

        # Build keyword list from domain + problem words
        domain_kws  = DOMAIN_KEYWORDS.get(domain, [])
        # Also add keywords from adjacent domains when domain is generic
        if domain in ("other", "software", "cloud"):
            domain_kws += DOMAIN_KEYWORDS.get("cloud", []) + DOMAIN_KEYWORDS.get("software", [])
        problem_kws = [w.lower() for w in re.split(r'\W+', problem) if len(w) > 3]
        keywords    = list(dict.fromkeys(domain_kws + problem_kws))[:12]

        for tbl in tables:
            cols_meta = tbl.columns_meta or {}
            all_cols  = list(cols_meta.keys())
            if not all_cols:
                continue

            # Text columns to search keywords in
            search_cols = [c for c in all_cols
                           if cols_meta[c].get("role") not in ("contact_email","manager_email",
                                                                "director_email","ops_email")][:8]

            # Always fetch ALL rows from every table then score by relevance
            try:
                unique_rows = fresh_db.execute(
                    text(f'SELECT * FROM "{tbl.table_name}" LIMIT {limit}')
                ).fetchall()
            except Exception:
                try: fresh_db.rollback()
                except Exception: pass
                continue

            # Score rows by keyword relevance — most relevant float to top
            if keywords and unique_rows:
                scored = []
                for row in unique_rows:
                    row_str = " ".join(str(v).lower() for v in row if v)
                    score   = sum(1 for kw in keywords if kw in row_str)
                    scored.append((score, row))
                scored.sort(key=lambda x: x[0], reverse=True)
                unique_rows = [r for _, r in scored]

            # Get ACTUAL column order from DB — never assume order
            try:
                probe = fresh_db.execute(
                    text(f'SELECT * FROM "{tbl.table_name}" LIMIT 1')
                )
                actual_col_names = list(probe.keys())
            except Exception:
                actual_col_names = ["id", "_uploaded_at", "_uploaded_by"] + all_cols

            for row in unique_rows:
                row_dict = dict(zip(actual_col_names, row))
                row_dict["_table_name"]   = tbl.table_name
                row_dict["_display_name"] = tbl.display_name
                row_dict["_columns_meta"] = cols_meta
                all_rows.append(row_dict)

            meta.append({
                "table_name":   tbl.table_name,
                "display_name": tbl.display_name,
                "columns_meta": cols_meta,
            })

        # Sort all rows across ALL tables by keyword score, best first
        if keywords:
            def row_score(r):
                row_str = " ".join(str(v).lower() for v in r.values() if v and not str(v).startswith("_"))
                return sum(1 for kw in keywords if kw in row_str)
            all_rows.sort(key=row_score, reverse=True)

        return all_rows[:limit], meta

    finally:
        fresh_db.close()


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — BUILD ASSET SUMMARY FOR PROMPT
# ─────────────────────────────────────────────────────────────────────────────

def build_asset_summary(rows: list) -> str:
    """
    Build a compact asset list for the Claude prompt.
    Each row shows only the values that are useful for identification.
    """
    if not rows:
        return "No specific assets found."

    lines = []
    for i, row in enumerate(rows[:25], 1):
        cols_meta = row.get("_columns_meta", {})
        parts     = []
        for col, val in row.items():
            if col.startswith("_") or not val:
                continue
            role = cols_meta.get(col, {}).get("role", "other")
            if role in SKIP_ROLES:
                continue
            parts.append(f"{col}={val}")
        if parts:
            lines.append(f"  {i}. [{row.get('_display_name','?')}] {', '.join(parts)}")

    return "\n".join(lines) if lines else "No assets found."


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — GENERATE QUESTIONS
# ─────────────────────────────────────────────────────────────────────────────

QUESTION_PROMPT = """You are an IT support triage assistant. A user reported an IT issue and needs it routed to the right engineer.

User problem: "{problem}"

Here are the actual assets in the system that could be affected:
{asset_list}

Your task: Generate 2-4 questions that will identify EXACTLY which asset is affected.

RULES:
1. Look at the asset list above. Find columns that DIFFERENTIATE between the assets.
   Ask about the column that eliminates the MOST candidates first.
   Example: if all assets are in Singapore but different environments, ask about environment.
   Example: if 3 are Oracle and 1 is MySQL, ask "Which database: Oracle or MySQL?"

2. Use the ACTUAL VALUES from the asset list as the answer options.
   Example: if server_name values are jenkins-prod-01, jenkins-prod-02, jenkins-stg-01 — use those exact names.
   Example: if db_engine values are Oracle, MySQL, PostgreSQL — use those exact names.

3. Phrase questions in plain English that any employee understands:
   GOOD: "Which database are you using? (Oracle / MySQL / PostgreSQL)"
   GOOD: "Which server is affected? (jenkins-prod-01 / jenkins-prod-02)"  
   GOOD: "Which region? (ap-south-1 / asia-southeast1 / uksouth)"
   BAD:  "Which team vertical?" — employee doesn't know this
   BAD:  "Which environment?" — too vague, say production/staging/development
   BAD:  "Which business unit?" — too internal

4. If a column has only 1 distinct value across all assets — skip it, it won't help narrow down.

5. Ask the most discriminating question first (eliminates most candidates).

6. Never ask about email addresses, IP addresses, MAC addresses, VLAN IDs, or internal team codes.

Respond ONLY with a valid JSON array of question strings. No explanation outside JSON."""


def generate_questions(db: Session, domain: str, problem: str) -> List[str]:
    """
    Fetch real assets → build prompt → ask Claude for targeted questions.
    Single API call, low latency.
    """
    rows, meta = fetch_assets(db, domain, problem)

    if not rows:
        # Fallback — no assets found
        return [
            "Which system or application is affected?",
            "Is this a production or test system?",
        ]

    asset_list = build_asset_summary(rows)

    prompt = QUESTION_PROMPT.format(
        problem    = problem[:300],
        asset_list = asset_list,
    )

    try:
        response = _client.messages.create(
            model      = "claude-sonnet-4-5",
            max_tokens = 500,
            messages   = [{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"): raw = raw[4:]
            raw = raw.strip()

        questions = json.loads(raw)
        if isinstance(questions, list) and questions and all(isinstance(q, str) for q in questions):
            print(f"\n  [AssetID] {len(questions)} questions generated for domain={domain}")
            for i, q in enumerate(questions, 1):
                print(f"    Q{i}: {q}")
            return questions[:4]

    except Exception as e:
        print(f"  [AssetID] Question generation error: {e}")

    # Fallback — build from column samples directly
    return _fallback_questions(rows)


def _fallback_questions(rows: list) -> List[str]:
    """Build basic questions from actual column values without Claude."""
    if not rows:
        return ["Which system is affected?", "Which environment?"]

    # Find columns with 2-8 distinct values
    col_values: Dict[str, set] = {}
    cols_meta  = rows[0].get("_columns_meta", {})

    for row in rows:
        for col, val in row.items():
            if col.startswith("_") or not val:
                continue
            role = cols_meta.get(col, {}).get("role", "other")
            if role in SKIP_ROLES:
                continue
            if col not in col_values:
                col_values[col] = set()
            col_values[col].add(str(val))

    # Sort by distinct count (most discriminating first)
    useful = [(col, vals) for col, vals in col_values.items() if 2 <= len(vals) <= 10]
    useful.sort(key=lambda x: len(x[1]))

    questions = []
    for col, vals in useful[:3]:
        label   = col.replace("_", " ").title()
        options = " / ".join(sorted(vals)[:6])
        questions.append(f"Which {label}? ({options})")

    return questions if questions else ["Which system is affected?", "Which environment?"]


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — EXTRACT FIELD FROM ANSWER
# ─────────────────────────────────────────────────────────────────────────────

# Roles that are useful for question answering (not skip roles)
QUESTION_ROLES = {"identifier", "environment", "region", "application", "team", "os", "power_state"}


def extract_field_from_answer(question: str, answer: str, rows: list) -> dict:
    """
    Map a user answer back to a column+value for DB filtering.

    Strategy (in priority order):
    1. Exact match in QUESTION_ROLES columns
    2. Exact match in ANY column (catches device_type=Router, manufacturer=Cisco etc)
    3. Substring match in QUESTION_ROLES columns only (avoids hostname false positives)
    """
    if not rows or not answer.strip():
        return {"column": None, "value": None}

    a_lower   = answer.strip().lower()
    cols_meta = rows[0].get("_columns_meta", {})

    # Build two maps:
    # 1. question_col_values — QUESTION_ROLES only (for substring matching)
    # 2. all_col_values — all non-skip columns (for exact matching only)
    question_col_values: Dict[str, List[str]] = {}
    all_col_values: Dict[str, List[str]]      = {}

    for row in rows:
        for col, val in row.items():
            if col.startswith("_") or not val:
                continue
            role = cols_meta.get(col, {}).get("role", "other")
            if role in SKIP_ROLES:
                continue
            sv = str(val)
            # All columns for exact match
            if col not in all_col_values:
                all_col_values[col] = []
            if sv not in all_col_values[col]:
                all_col_values[col].append(sv)
            # Question roles only for substring match
            if role in QUESTION_ROLES:
                if col not in question_col_values:
                    question_col_values[col] = []
                if sv not in question_col_values[col]:
                    question_col_values[col].append(sv)

    # Pass 1: Exact match in QUESTION_ROLES columns
    for col, vals in question_col_values.items():
        for v in vals:
            if a_lower == v.lower():
                return {"column": col, "value": v}

    # Pass 2: Exact match in ALL columns (catches device_type, manufacturer etc)
    for col, vals in all_col_values.items():
        for v in vals:
            if a_lower == v.lower():
                return {"column": col, "value": v}

    # Pass 3: Substring match — QUESTION_ROLES only, avoid identifier false positives
    best_col, best_val, best_score = None, None, 0
    for col, vals in question_col_values.items():
        role = cols_meta.get(col, {}).get("role", "other")
        # Never substring-match identifier columns — too many false positives
        # e.g. "Router" matching "core-router-mumbai-01"
        if role == "identifier":
            continue
        for v in vals:
            v_lower = v.lower()
            if a_lower in v_lower or v_lower in a_lower:
                score = len(v_lower) if a_lower in v_lower else len(a_lower)
                if isinstance(score, int) and score > best_score:
                    best_score = score
                    best_col   = col
                    best_val   = v

    if best_col:
        return {"column": best_col, "value": best_val}

    best_col   = None
    best_val   = None
    best_score = 0

    for col, vals in col_values.items():
        for v in vals:
            v_lower = v.lower()
            # Exact match — highest priority
            if a_lower == v_lower:
                return {"column": col, "value": v}
            # Substring match
            if a_lower in v_lower or v_lower in a_lower:
                score = len(v_lower) if a_lower in v_lower else len(a_lower)
                if isinstance(score, int) and score > best_score:
                    best_score = score
                    best_col   = col
                    best_val   = v

    if best_col:
        return {"column": best_col, "value": best_val}

    # Last resort — map by question keywords
    q = question.lower()
    role_hints = [
        (["server", "hostname", "device", "instance", "which one", "name"], "identifier"),
        (["region", "location", "office", "data centre", "where"],          "region"),
        (["database", "db", "engine", "which db"],                          "application"),
        (["environment", "production", "staging", "live", "test"],          "environment"),
        (["team", "department"],                                             "team"),
    ]
    for keywords, role in role_hints:
        if any(kw in q for kw in keywords):
            col = next((c for c, m in cols_meta.items() if m.get("role") == role), None)
            if col:
                return {"column": col, "value": answer.strip()}

    return {"column": None, "value": None}


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — PROGRESSIVE MATCH
# ─────────────────────────────────────────────────────────────────────────────

def progressive_match(db: Session, collected_filters: dict, candidate_rows: list) -> dict:
    """
    Filter candidate_rows by collected_filters.
    Returns:
      matched:    best matching row dict (with owner info) or None
      candidates: count of rows still matching
      confident:  True only if exactly 1 row matches
    """
    if not collected_filters or not candidate_rows:
        return {"matched": None, "candidates": 0, "confident": False}

    matching = []
    for row in candidate_rows:
        match = True
        for col, val in collected_filters.items():
            row_val = str(row.get(col, "")).lower()
            if not row_val or val.lower() not in row_val:
                match = False
                break
        if match:
            matching.append(row)

    if not matching:
        # Relax filters — try with one fewer filter
        filter_items = list(collected_filters.items())
        for i in range(len(filter_items) - 1, -1, -1):
            relaxed = dict(filter_items[:i] + filter_items[i+1:])
            if not relaxed:
                break
            relaxed_matching = [
                row for row in candidate_rows
                if all(
                    val.lower() in str(row.get(col, "")).lower()
                    for col, val in relaxed.items()
                )
            ]
            if relaxed_matching:
                return {
                    "matched":    _extract_owner(relaxed_matching[0]),
                    "candidates": len(relaxed_matching),
                    "confident":  len(relaxed_matching) == 1,
                }
        return {"matched": None, "candidates": 0, "confident": False}

    best = matching[0]
    return {
        "matched":    _extract_owner(best),
        "candidates": len(matching),
        "confident":  len(matching) == 1,
    }


def _extract_owner(row: dict) -> dict:
    """Extract ownership info from a matched asset row using column roles."""
    cols_meta = row.get("_columns_meta", {})

    # Build role → first column map
    role_map = {}
    for col, meta in cols_meta.items():
        role = meta.get("role", "other")
        if role not in role_map:
            role_map[role] = col

    def get(role):
        col = role_map.get(role)
        return str(row.get(col, "")) if col else ""

    return {
        "table_name":    row.get("_table_name", ""),
        "display_name":  row.get("_display_name", ""),
        "contact_email": get("contact_email"),
        "manager_email": get("manager_email"),
        "director_email":get("director_email"),
        "ops_email":     get("ops_email"),
        "identifier":    get("identifier"),
        "environment":   get("environment"),
        "team":          get("team"),
        "row":           {k: str(v) for k, v in row.items() if not k.startswith("_") and v},
    }