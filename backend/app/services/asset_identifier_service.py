# Location: backend/app/services/asset_identifier_service.py
#
# PURPOSE:
#   Given a user problem + domain, fetch relevant assets from ALL dynamic tables,
#   then ask Claude to generate USER-FRIENDLY questions to pinpoint ONE asset.
#
#   Questions must be answerable by a REGULAR USER — not a technical person.
#   Ask about: location, environment, scope, impact — NOT hostnames or IPs.
#
#   After each answer, search all tables for a matching row.
#   If exactly 1 row found → confident match → route to owner.

import json
import logging
import re
from typing import Optional, List, Dict
from sqlalchemy.orm import Session
from sqlalchemy import text
import anthropic

from app.core.config import settings

logger = logging.getLogger(__name__)

_client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

# ─────────────────────────────────────────────────────────────────────────────
# DOMAIN KEYWORDS
# ─────────────────────────────────────────────────────────────────────────────

DOMAIN_KEYWORDS = {
    "networking":          ["router", "switch", "firewall", "vpn", "network", "dns", "proxy", "load balancer"],
    "security":            ["firewall", "waf", "ids", "siem", "dlp", "nessus", "security"],
    "database":            ["oracle", "mysql", "postgres", "mongodb", "redis", "cassandra", "elasticsearch", "database", "db"],
    "devops":              ["jenkins", "gitlab", "kubernetes", "k8s", "nexus", "sonar", "ci", "pipeline", "deployment"],
    "software":            ["app", "api", "microservice", "portal", "gateway", "payment", "service", "checkout"],
    "cloud":               ["ec2", "gcp", "azure", "s3", "cloud", "vm", "instance", "bucket"],
    "infrastructure":      ["hypervisor", "vcenter", "esxi", "backup", "storage", "monitoring"],
    "hardware":            ["blade", "server", "workstation", "printer"],
    "email_communication": ["exchange", "smtp", "mail", "teams", "slack", "email"],
    "erp_business_apps":   ["sap", "oracle ebs", "salesforce", "servicenow", "erp", "crm"],
    "identity_access":     ["ldap", "active directory", "sso", "pam", "radius", "login", "auth"],
    "endpoint_management": ["mdm", "antivirus", "patch", "endpoint", "laptop", "desktop"],
    "other":               ["payment", "checkout", "purchase", "order", "invoice", "service"],
}

SKIP_ROLES = {"contact_email", "manager_email", "director_email", "ops_email", "ip"}

# Columns that a regular user would NOT know
TECHNICAL_COLUMNS = {
    "hostname", "device_id", "asset_tag", "mac_address", "private_ip", "public_ip",
    "vlan_id", "rack_unit", "firmware_version", "port_count", "throughput_gbps",
    "purchase_date", "warranty_expiry", "uptime_days", "subnet", "model",
    "primary_owner_email", "it_manager_email", "it_director_email", "infra_ops_email",
}

# Columns a regular user CAN answer about
USER_FRIENDLY_COLUMNS = {
    "data_centre", "environment", "device_type", "manufacturer",
    "business_unit", "team_name", "power_status", "criticality",
    "sla_tier", "protocol",
}


# ─────────────────────────────────────────────────────────────────────────────
# FETCH ASSETS
# ─────────────────────────────────────────────────────────────────────────────

def fetch_assets(db: Session, domain: str, problem: str, limit: int = 40) -> tuple:
    from app.services.dynamic_table_service import get_all_tables
    from app.core.database import SessionLocal

    fresh_db = SessionLocal()
    try:
        tables   = get_all_tables(fresh_db)
        all_rows = []
        meta     = []

        domain_kws  = DOMAIN_KEYWORDS.get(domain, [])
        if domain in ("other", "software", "cloud"):
            domain_kws += DOMAIN_KEYWORDS.get("cloud", []) + DOMAIN_KEYWORDS.get("software", [])
        problem_kws = [w.lower() for w in re.split(r'\W+', problem) if len(w) > 3]
        keywords    = list(dict.fromkeys(domain_kws + problem_kws))[:12]

        for tbl in tables:
            cols_meta = tbl.columns_meta or {}
            all_cols  = list(cols_meta.keys())
            if not all_cols:
                continue

            try:
                unique_rows = fresh_db.execute(
                    text(f'SELECT * FROM "{tbl.table_name}" LIMIT {limit}')
                ).fetchall()
            except Exception as _e:
                logger.warning("[AssetFetch] Query failed for table %s: %s", tbl.table_name, _e)
                try:
                    fresh_db.rollback()
                except Exception:
                    pass
                continue

            if keywords and unique_rows:
                scored = []
                for row in unique_rows:
                    row_str = " ".join(str(v).lower() for v in row if v)
                    score   = sum(1 for kw in keywords if kw in row_str)
                    scored.append((score, row))
                scored.sort(key=lambda x: x[0], reverse=True)
                unique_rows = [r for _, r in scored]

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

        if keywords:
            def row_score(r):
                row_str = " ".join(str(v).lower() for v in r.values() if v and not str(v).startswith("_"))
                return sum(1 for kw in keywords if kw in row_str)
            all_rows.sort(key=row_score, reverse=True)

        return all_rows[:limit], meta

    finally:
        fresh_db.close()


# ─────────────────────────────────────────────────────────────────────────────
# BUILD ASSET SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

def build_asset_summary(rows: list) -> str:
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
# GENERATE USER-FRIENDLY QUESTIONS
# ─────────────────────────────────────────────────────────────────────────────

QUESTION_PROMPT = """You are an IT support triage assistant helping route a ticket to the right engineer.

User problem: "{problem}"

Assets that could be affected:
{asset_list}

Generate 1-2 questions to identify exactly which asset is affected.

RULES:
1. Questions must be answerable by a NON-TECHNICAL employee (finance, HR, regular office worker).
   They know: their city, their office location, whether something is live or test.
   They do NOT know: server names, IP addresses, hostnames, VLANs, rack units, model numbers.

2. Look at EVERY column in the asset list. For each column decide:
   - Would a regular employee know this? → ask about it in plain English
   - Is it too technical? → skip it entirely

3. Convert technical values to plain English:
   - data_centre "DC-Mumbai-01" → ask "Which city? (Mumbai / London / Singapore)"
   - environment "Production" → ask "Is this your live system or a test system?"
   - region "ap-south-1" → ask "Which region? (Asia / Europe / Americas)"
   - team_name "Network Operations" → ask "Which team uses this? (Network / Cloud / Security)"
   - Any code-like value → convert to plain English or skip

4. Never ask about: device type (AI knows from problem), hostname, IP, MAC, VLAN, asset tag,
   rack unit, firmware version, model number, purchase date, warranty.

5. Maximum 2 questions. Use the actual distinct values from the asset list as options.

Respond ONLY with a JSON array of strings. No explanation."""


def generate_questions(db: Session, domain: str, problem: str) -> List[str]:
    rows, meta = fetch_assets(db, domain, problem)

    if not rows:
        return [
            "Which office or location are you in?",
            "Is this a Production or Staging system?",
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
            logger.debug("[AssetID] %d questions generated for domain=%s", len(questions), domain)
            return questions[:3]

    except Exception as e:
        logger.warning("[AssetID] Question generation error: %s", e)

    return _fallback_questions(rows)


def _fallback_questions(rows: list) -> List[str]:
    if not rows:
        return ["Which office or location are you in?", "Is this Production or Staging?"]

    col_values: Dict[str, set] = {}
    cols_meta  = rows[0].get("_columns_meta", {})

    for row in rows:
        for col, val in row.items():
            if col.startswith("_") or not val:
                continue
            if col.lower() in TECHNICAL_COLUMNS:
                continue
            role = cols_meta.get(col, {}).get("role", "other")
            if role in SKIP_ROLES:
                continue
            if col not in col_values:
                col_values[col] = set()
            col_values[col].add(str(val))

    useful = [(col, vals) for col, vals in col_values.items() if 2 <= len(vals) <= 8]
    useful.sort(key=lambda x: len(x[1]))

    questions = []
    for col, vals in useful[:2]:
        if col == "data_centre":
            cities = []
            for v in sorted(vals)[:5]:
                city = v.replace("DC-", "").split("-")[0]
                cities.append(city)
            questions.append(f"Which city are you based in? ({' / '.join(cities)})")
        elif col == "environment":
            questions.append("Is this affecting your live/production systems or a test environment?")
        elif col == "device_type":
            pass  # Never ask device type — AI knows from problem
        else:
            label   = col.replace("_", " ").title()
            options = " / ".join(sorted(vals)[:5])
            questions.append(f"Which {label}? ({options})")

    questions = [q for q in questions if q]  # remove empty
    return questions if questions else [
        "Which city are you based in?",
        "Is this affecting your live/production systems or a test environment?",
    ]


# ─────────────────────────────────────────────────────────────────────────────
# EXTRACT FIELD FROM ANSWER
# ─────────────────────────────────────────────────────────────────────────────

def extract_field_from_answer(question: str, answer: str, rows: list) -> dict:
    if not rows or not answer.strip():
        return {"column": None, "value": None}

    a_lower   = answer.strip().lower()
    cols_meta = rows[0].get("_columns_meta", {})

    all_col_values: Dict[str, List[str]] = {}

    for row in rows:
        for col, val in row.items():
            if col.startswith("_") or not val:
                continue
            role = cols_meta.get(col, {}).get("role", "other")
            if role in SKIP_ROLES:
                continue
            sv = str(val)
            if col not in all_col_values:
                all_col_values[col] = []
            if sv not in all_col_values[col]:
                all_col_values[col].append(sv)

    # Pass 1: Exact match
    for col, vals in all_col_values.items():
        for v in vals:
            if a_lower == v.lower():
                return {"column": col, "value": v}

    # Pass 2: Substring match (non-technical columns only)
    best_col, best_val, best_score = None, None, 0
    for col, vals in all_col_values.items():
        if col.lower() in TECHNICAL_COLUMNS:
            continue
        for v in vals:
            v_lower = v.lower()
            if a_lower in v_lower or v_lower in a_lower:
                score = len(v_lower)
                if score > best_score:
                    best_score = score
                    best_col   = col
                    best_val   = v

    if best_col:
        return {"column": best_col, "value": best_val}

    # Pass 3: City → data_centre mapping
    CITY_MAP = {
        "mumbai":    "DC-Mumbai",
        "london":    "DC-London",
        "singapore": "DC-Singapore",
        "sydney":    "DC-Sydney",
        "new york":  "DC-NewYork",
        "frankfurt": "DC-Frankfurt",
        "tokyo":     "DC-Tokyo",
        "dubai":     "DC-Dubai",
    }
    for city, dc_prefix in CITY_MAP.items():
        if city in a_lower:
            # Find the matching data_centre value in assets
            if "data_centre" in all_col_values:
                for v in all_col_values["data_centre"]:
                    if dc_prefix.lower() in v.lower():
                        return {"column": "data_centre", "value": v}
            # Fallback — return city as value
            return {"column": "data_centre", "value": answer.strip()}

    # Pass 4: Environment plain English mapping
    ENV_MAP = {
        "live": "Production", "production": "Production", "prod": "Production",
        "real": "Production", "actual": "Production",
        "test": "Staging", "staging": "Staging", "dev": "Development",
        "development": "Development", "sandbox": "Development",
    }
    for keyword, env_val in ENV_MAP.items():
        if keyword in a_lower:
            if "environment" in all_col_values:
                for v in all_col_values["environment"]:
                    if env_val.lower() in v.lower():
                        return {"column": "environment", "value": v}
            return {"column": "environment", "value": env_val}

    # Pass 5: Question keyword hints
    q = question.lower()
    role_hints = [
        (["city", "location", "office", "based in", "where"],         "data_centre"),
        (["environment", "production", "staging", "live", "test"],     "environment"),
        (["team", "department", "owns"],                               "team_name"),
        (["type of system", "device type", "what type"],               "device_type"),
        (["down", "offline", "running", "working"],                    "power_status"),
    ]
    for keywords, col in role_hints:
        if any(kw in q for kw in keywords):
            if col in all_col_values:
                return {"column": col, "value": answer.strip()}

    return {"column": None, "value": None}


# ─────────────────────────────────────────────────────────────────────────────
# PROGRESSIVE MATCH
# ─────────────────────────────────────────────────────────────────────────────

def progressive_match(db: Session, collected_filters: dict, candidate_rows: list) -> dict:
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
    cols_meta = row.get("_columns_meta", {})

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
        "director_email": get("director_email"),
        "ops_email":     get("ops_email"),
        "identifier":    get("identifier"),
        "environment":   get("environment"),
        "team":          get("team"),
        "row":           {k: str(v) for k, v in row.items() if not k.startswith("_") and v},
    }