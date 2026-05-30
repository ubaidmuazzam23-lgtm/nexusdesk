# Location: backend/app/services/dynamic_table_service.py
#
# PURPOSE:
#   Core service for the dynamic multi-table asset registry system.
#
#   Key responsibilities:
#     1. Parse any CSV structure
#     2. Ask Claude if the CSV can merge with an existing table
#     3. Create a new dynamic PostgreSQL table if needed
#     4. Insert rows into the right table
#     5. Query across ALL tables for routing and question generation
#
#   Design principle:
#     No hardcoded column names anywhere. Claude determines the semantic
#     role of each column (identifier, contact_email, manager_email etc.)
#     at upload time. The system stores this in columns_meta and uses it
#     for routing and question generation at chat time.

import csv
import io
import json
import re
import secrets
import string
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from fastapi import HTTPException
from sqlalchemy import text, inspect
from sqlalchemy.orm import Session

import anthropic

from app.core.config import settings
from app.models.asset_table_registry import AssetTableRegistry

_client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


# ─────────────────────────────────────────────────────────────────────────────
# COLUMN SEMANTIC ROLES
# Used by routing to identify what each column means.
# ─────────────────────────────────────────────────────────────────────────────

ROLE_IDENTIFIER    = "identifier"       # uniquely identifies the asset (hostname, instance_name)
ROLE_ENVIRONMENT   = "environment"      # Production / Staging / Dev
ROLE_TEAM          = "team"             # owning team
ROLE_REGION        = "region"           # data centre / cloud region
ROLE_IP            = "ip"               # IP address
ROLE_OS            = "os"               # operating system
ROLE_POWER         = "power_state"      # running / stopped / terminated
ROLE_APP           = "application"      # application name
ROLE_CONTACT       = "contact_email"    # primary owner email → routing priority 1
ROLE_MANAGER       = "manager_email"    # manager email → routing priority 2
ROLE_DIRECTOR      = "director_email"   # director email
ROLE_OPS           = "ops_email"        # ops/cloudops email
ROLE_OTHER         = "other"            # everything else


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — PARSE CSV
# ─────────────────────────────────────────────────────────────────────────────

def _norm_col(name: str) -> str:
    """Normalise column name to safe PostgreSQL identifier."""
    s = name.strip().lower()
    s = re.sub(r'[^a-z0-9_]', '_', s)
    s = re.sub(r'_+', '_', s).strip('_')
    if s and s[0].isdigit():
        s = 'col_' + s
    return s or 'col'


def parse_csv_raw(content: bytes) -> Tuple[List[str], List[Dict[str, str]]]:
    """
    Parse CSV bytes into:
      - original_headers: list of original column names in order
      - rows: list of dicts {normalised_col: value}

    Returns (original_headers, rows)
    """
    text_content = content.decode('utf-8', errors='ignore')
    reader       = csv.DictReader(io.StringIO(text_content))

    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV has no headers")

    original_headers = list(reader.fieldnames)
    norm_headers     = [_norm_col(h) for h in original_headers]

    # Deduplicate normalised headers
    seen = {}
    deduped = []
    for h in norm_headers:
        if h in seen:
            seen[h] += 1
            deduped.append(f"{h}_{seen[h]}")
        else:
            seen[h] = 0
            deduped.append(h)
    norm_headers = deduped

    rows = []
    for raw_row in reader:
        row = {}
        for orig, norm in zip(original_headers, norm_headers):
            val = raw_row.get(orig, '').strip()
            if val:
                row[norm] = val
        if row:
            rows.append(row)

    return original_headers, rows


def _get_samples(rows: List[Dict], col: str, max_samples: int = 6) -> List[str]:
    """Get distinct non-empty sample values for a column."""
    seen = set()
    out  = []
    for row in rows:
        v = row.get(col, '').strip()
        if v and v not in seen:
            seen.add(v)
            out.append(v)
        if len(out) >= max_samples:
            break
    return out


def _guess_data_type(col_name: str, samples: List[str]) -> str:
    """Quick heuristic to guess data type from name and samples."""
    n = col_name.lower()
    if 'email' in n or 'mail' in n:
        return 'email'
    if 'ip' in n or 'address' in n:
        if samples and re.match(r'\d+\.\d+\.\d+\.\d+', samples[0]):
            return 'ip'
    if samples and len(set(samples)) <= 8:
        return 'enum'
    try:
        if samples:
            int(samples[0])
            return 'integer'
    except Exception:
        pass
    return 'text'


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — AI COLUMN ANALYSIS
# Ask Claude to assign semantic roles to each column and decide
# if the CSV can merge with any existing table.
# ─────────────────────────────────────────────────────────────────────────────

ANALYSE_PROMPT = """You are analysing a CSV file of IT infrastructure assets.

Here are the columns and sample values from the new CSV:
{new_csv_schema}

Here are the existing asset tables in the system:
{existing_tables}

Your tasks:

TASK 1 — Assign a semantic role to each column of the NEW CSV.
Roles available:
  identifier    = uniquely identifies the asset (hostname, server name, instance name, asset ID)
  environment   = deployment environment (Production, Staging, Dev, etc.)
  team          = owning team or business unit
  region        = data centre location or cloud region
  ip            = IP address (private or public)
  os            = operating system
  power_state   = running/stopped/terminated status
  application   = application or service name
  contact_email = primary owner/contact email (used for routing - MOST IMPORTANT)
  manager_email = manager or team lead email (used for routing fallback)
  director_email= director or head email
  ops_email     = operations/infra/cloudops email
  other         = anything else (cost centre, serial number, rack location, etc.)

TASK 2 — Decide if the new CSV can MERGE with any existing table.
Merge means: the data is about the same type of assets with similar columns.
Even if column names differ (HOSTNAME vs SERVER_NAME vs HOST_NAME), if they 
represent the same concept, it can merge.
A merge is appropriate when 60%+ of columns serve the same semantic purpose.

Respond ONLY with valid JSON in this exact format:
{{
  "column_roles": {{
    "normalised_col_name": "role",
    ...
  }},
  "merge_decision": {{
    "can_merge": true or false,
    "merge_with_table": "table_name or null",
    "confidence": 0.0 to 1.0,
    "reason": "brief explanation"
  }}
}}

No explanation outside the JSON."""


def analyse_csv_with_ai(
    original_headers: List[str],
    norm_headers: List[str],
    rows: List[Dict],
    existing_tables: List[AssetTableRegistry],
) -> Dict:
    """
    Ask Claude to:
    1. Assign semantic roles to each column
    2. Decide if this CSV can merge with an existing table

    Returns the parsed JSON response from Claude.
    """
    # Build new CSV schema description
    new_schema_lines = []
    for orig, norm in zip(original_headers, norm_headers):
        samples   = _get_samples(rows, norm)
        data_type = _guess_data_type(norm, samples)
        new_schema_lines.append(
            f"  {norm} (original: '{orig}', type: {data_type}, "
            f"samples: {samples})"
        )
    new_csv_schema = "\n".join(new_schema_lines)

    # Build existing tables description
    if existing_tables:
        et_lines = []
        for tbl in existing_tables:
            et_lines.append(f"\nTable: {tbl.table_name} (display: '{tbl.display_name}', {tbl.row_count} rows)")
            for col, meta in (tbl.columns_meta or {}).items():
                et_lines.append(
                    f"  {col} (role: {meta.get('role','?')}, "
                    f"samples: {meta.get('samples', [])[:3]})"
                )
        existing_tables_str = "\n".join(et_lines)
    else:
        existing_tables_str = "None — this will be the first table."

    prompt = ANALYSE_PROMPT.format(
        new_csv_schema   = new_csv_schema,
        existing_tables  = existing_tables_str,
    )

    try:
        response = _client.messages.create(
            model      = "claude-sonnet-4-5",
            max_tokens = 1200,
            messages   = [{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()

        # Strip markdown fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        result = json.loads(raw)
        print(f"\n  [DynamicTable] AI analysis complete:")
        print(f"    Merge: {result['merge_decision']['can_merge']} — {result['merge_decision']['reason']}")
        return result

    except Exception as e:
        print(f"  [DynamicTable] AI analysis error: {e}")
        # Fallback — no merge, basic role assignment
        column_roles = {}
        for norm in norm_headers:
            column_roles[norm] = _guess_role_heuristic(norm)
        return {
            "column_roles": column_roles,
            "merge_decision": {
                "can_merge":        False,
                "merge_with_table": None,
                "confidence":       0.0,
                "reason":           "AI analysis failed — creating new table",
            },
        }


def _guess_role_heuristic(col: str) -> str:
    """Fast heuristic role guesser as fallback."""
    c = col.lower()
    if any(x in c for x in ['email', 'mail', 'contact']):
        if any(x in c for x in ['manager', 'mgr']):     return ROLE_MANAGER
        if any(x in c for x in ['director', 'dir']):    return ROLE_DIRECTOR
        if any(x in c for x in ['ops', 'infra', 'cloudops']): return ROLE_OPS
        return ROLE_CONTACT
    if any(x in c for x in ['hostname', 'server_name', 'instance', 'host', 'node', 'device']): return ROLE_IDENTIFIER
    if any(x in c for x in ['env', 'environment', 'tier']): return ROLE_ENVIRONMENT
    if any(x in c for x in ['team', 'squad', 'department', 'business_unit']): return ROLE_TEAM
    if any(x in c for x in ['region', 'location', 'dc', 'zone', 'site']): return ROLE_REGION
    if any(x in c for x in ['ip', 'address', 'subnet']): return ROLE_IP
    if any(x in c for x in ['os', 'operating', 'distrib', 'platform']): return ROLE_OS
    if any(x in c for x in ['power', 'state', 'status', 'running']): return ROLE_POWER
    if any(x in c for x in ['app', 'application', 'service', 'workload']): return ROLE_APP
    return ROLE_OTHER


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — CREATE DYNAMIC TABLE
# ─────────────────────────────────────────────────────────────────────────────

def _gen_table_name(display_name: str, db: Session) -> str:
    """Generate a unique safe PostgreSQL table name."""
    base = re.sub(r'[^a-z0-9]', '_', display_name.lower().strip())
    base = re.sub(r'_+', '_', base).strip('_')[:30]
    base = f"dyn_asset_{base}"

    # Ensure uniqueness
    existing = {row.table_name for row in db.query(AssetTableRegistry.table_name).all()}
    candidate = base
    suffix    = 1
    while candidate in existing:
        candidate = f"{base}_{suffix}"
        suffix   += 1
    return candidate


def create_dynamic_table(
    db: Session,
    table_name: str,
    norm_headers: List[str],
) -> None:
    """
    Create a new PostgreSQL table dynamically with:
      - id (UUID primary key)
      - _uploaded_at (timestamp)
      - _uploaded_by (text)
      - one TEXT column per CSV column
    """
    # Check if table already exists
    inspector = inspect(db.bind)
    if table_name in inspector.get_table_names():
        print(f"  [DynamicTable] Table {table_name} already exists — skipping create")
        return

    # Build column definitions — all TEXT for maximum flexibility
    col_defs = ",\n    ".join(
        f'"{col}" TEXT' for col in norm_headers
    )

    sql = f"""
    CREATE TABLE "{table_name}" (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        _uploaded_at    TIMESTAMP DEFAULT NOW(),
        _uploaded_by    TEXT,
        {col_defs}
    )
    """
    db.execute(text(sql))
    db.commit()
    print(f"  [DynamicTable] Created table: {table_name} with {len(norm_headers)} columns")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — INSERT ROWS
# ─────────────────────────────────────────────────────────────────────────────

def insert_rows(
    db: Session,
    table_name: str,
    rows: List[Dict],
    norm_headers: List[str],
    uploaded_by: str,
) -> int:
    """
    Insert CSV rows into the dynamic table.
    Only inserts columns that exist in the table.
    Returns number of rows inserted.
    """
    if not rows:
        return 0

    # Get actual columns in the table
    inspector    = inspect(db.bind)
    table_cols   = {col['name'] for col in inspector.get_columns(table_name)}
    valid_cols   = [c for c in norm_headers if c in table_cols]

    inserted = 0
    for row in rows:
        col_names = []
        col_vals  = []
        for col in valid_cols:
            val = row.get(col)
            if val is not None:
                col_names.append(f'"{col}"')
                col_vals.append(val)

        if not col_names:
            continue

        col_names.append('_uploaded_by')
        col_vals.append(uploaded_by)

        placeholders = ', '.join(f':val_{i}' for i in range(len(col_vals)))
        col_str      = ', '.join(col_names)
        params       = {f'val_{i}': v for i, v in enumerate(col_vals)}

        db.execute(
            text(f'INSERT INTO "{table_name}" ({col_str}) VALUES ({placeholders})'),
            params,
        )
        inserted += 1

    db.commit()
    return inserted


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — HANDLE MERGE: add missing columns to existing table
# ─────────────────────────────────────────────────────────────────────────────

def merge_into_existing_table(
    db: Session,
    target_table_name: str,
    norm_headers: List[str],
    rows: List[Dict],
    uploaded_by: str,
) -> int:
    """
    Append rows from new CSV into an existing table.
    Adds any new columns that don't exist yet (ALTER TABLE ADD COLUMN).
    """
    inspector   = inspect(db.bind)
    table_cols  = {col['name'] for col in inspector.get_columns(target_table_name)}

    # Add any missing columns
    for col in norm_headers:
        if col not in table_cols:
            db.execute(text(f'ALTER TABLE "{target_table_name}" ADD COLUMN IF NOT EXISTS "{col}" TEXT'))
            print(f"  [DynamicTable] Added column '{col}' to {target_table_name}")

    db.commit()
    return insert_rows(db, target_table_name, rows, norm_headers, uploaded_by)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN UPLOAD HANDLER
# ─────────────────────────────────────────────────────────────────────────────

def upload_asset_csv(
    db: Session,
    content: bytes,
    display_name: str,
    uploaded_by: str,
    force_new_table: bool = False,
) -> dict:
    """
    Full upload pipeline:
      1. Parse CSV
      2. AI analyses columns + decides merge
      3. Create new table OR merge into existing
      4. Insert rows
      5. Update AssetTableRegistry
      6. Return result summary

    Args:
        content:         Raw CSV bytes
        display_name:    Human-readable name admin gave this upload
        uploaded_by:     Admin user ID
        force_new_table: Skip merge check and always create new table
    """
    # ── Parse ─────────────────────────────────────────────────────────────────
    original_headers, rows = parse_csv_raw(content)
    if not rows:
        raise HTTPException(status_code=400, detail="No valid rows found in CSV")

    norm_headers = [_norm_col(h) for h in original_headers]
    # Deduplicate
    seen = {}
    deduped = []
    for h in norm_headers:
        if h in seen:
            seen[h] += 1
            deduped.append(f"{h}_{seen[h]}")
        else:
            seen[h] = 0
            deduped.append(h)
    norm_headers = deduped

    print(f"\n  [DynamicTable] Uploading '{display_name}' — {len(rows)} rows, {len(norm_headers)} columns")

    # ── Get existing tables ────────────────────────────────────────────────────
    existing_tables = db.query(AssetTableRegistry).filter(
        AssetTableRegistry.is_active == True
    ).all()

    # ── AI analysis ───────────────────────────────────────────────────────────
    if force_new_table:
        ai_result = {
            "column_roles": {n: _guess_role_heuristic(n) for n in norm_headers},
            "merge_decision": {"can_merge": False, "merge_with_table": None,
                               "confidence": 1.0, "reason": "Force new table requested"},
        }
    else:
        ai_result = analyse_csv_with_ai(original_headers, norm_headers, rows, existing_tables)

    column_roles   = ai_result.get("column_roles", {})
    merge_decision = ai_result.get("merge_decision", {})

    # ── Build columns_meta ────────────────────────────────────────────────────
    columns_meta = {}
    for orig, norm in zip(original_headers, norm_headers):
        samples   = _get_samples(rows, norm)
        data_type = _guess_data_type(norm, samples)
        role      = column_roles.get(norm, ROLE_OTHER)
        columns_meta[norm] = {
            "original_name": orig,
            "samples":       samples,
            "distinct":      len(set(r.get(norm, '') for r in rows if r.get(norm))),
            "role":          role,
            "data_type":     data_type,
        }

    # ── Decide: merge or new table ─────────────────────────────────────────────
    merged        = False
    target_table  = None

    if merge_decision.get("can_merge") and merge_decision.get("merge_with_table"):
        merge_table_name = merge_decision["merge_with_table"]
        # Verify the table actually exists in AssetTableRegistry
        existing_entry = db.query(AssetTableRegistry).filter(
            AssetTableRegistry.table_name == merge_table_name
        ).first()

        if existing_entry:
            inserted = merge_into_existing_table(
                db, merge_table_name, norm_headers, rows, uploaded_by
            )
            # Update registry entry
            existing_entry.row_count   += inserted
            existing_entry.last_upload  = datetime.utcnow()
            existing_entry.updated_at   = datetime.utcnow()
            # Merge columns_meta — add any new columns
            merged_meta = dict(existing_entry.columns_meta or {})
            for col, meta in columns_meta.items():
                if col not in merged_meta:
                    merged_meta[col] = meta
            existing_entry.columns_meta = merged_meta
            db.commit()

            merged       = True
            target_table = existing_entry
            print(f"  [DynamicTable] Merged {inserted} rows into '{merge_table_name}'")

    if not merged:
        # Create new dynamic table
        table_name = _gen_table_name(display_name, db)
        create_dynamic_table(db, table_name, norm_headers)
        inserted = insert_rows(db, table_name, rows, norm_headers, uploaded_by)

        # Register in AssetTableRegistry
        registry_entry = AssetTableRegistry(
            table_name   = table_name,
            display_name = display_name,
            columns_meta = columns_meta,
            row_count    = inserted,
            last_upload  = datetime.utcnow(),
            uploaded_by  = uploaded_by,
        )
        db.add(registry_entry)
        db.commit()
        db.refresh(registry_entry)
        target_table = registry_entry
        print(f"  [DynamicTable] Created new table '{table_name}' with {inserted} rows")

    return {
        "table_name":    target_table.table_name,
        "display_name":  target_table.display_name,
        "inserted":      inserted,
        "total_rows":    target_table.row_count,
        "merged":        merged,
        "merge_reason":  merge_decision.get("reason", ""),
        "columns":       list(columns_meta.keys()),
        "column_roles":  {k: v["role"] for k, v in columns_meta.items()},
        "message":       (
            f"Merged {inserted} rows into '{target_table.display_name}'"
            if merged else
            f"Created new table '{target_table.display_name}' with {inserted} rows"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# QUERY HELPERS — used by routing and question generation
# ─────────────────────────────────────────────────────────────────────────────

def get_all_tables(db: Session) -> List[AssetTableRegistry]:
    """Return all active asset tables."""
    return db.query(AssetTableRegistry).filter(
        AssetTableRegistry.is_active == True
    ).order_by(AssetTableRegistry.created_at.asc()).all()


def get_table_stats(db: Session) -> List[dict]:
    """Return stats for each table — used by admin overview."""
    tables = get_all_tables(db)
    result = []
    for tbl in tables:
        try:
            count = db.execute(
                text(f'SELECT COUNT(*) FROM "{tbl.table_name}"')
            ).scalar() or 0
        except Exception:
            count = tbl.row_count

        result.append({
            "id":           str(tbl.id),
            "table_name":   tbl.table_name,
            "display_name": tbl.display_name,
            "row_count":    count,
            "columns":      list((tbl.columns_meta or {}).keys()),
            "column_roles": {k: v.get("role") for k, v in (tbl.columns_meta or {}).items()},
            "last_upload":  tbl.last_upload.isoformat() if tbl.last_upload else None,
            "created_at":   tbl.created_at.isoformat() if tbl.created_at else None,
        })
    return result


def query_table(
    db: Session,
    table_name: str,
    filters: Optional[Dict[str, str]] = None,
    search: Optional[str]             = None,
    limit: int  = 500,
    offset: int = 0,
) -> dict:
    """
    Query a single dynamic table with optional filters and search.
    Returns rows as list of dicts + total count.
    """
    tbl_entry = db.query(AssetTableRegistry).filter(
        AssetTableRegistry.table_name == table_name
    ).first()
    if not tbl_entry:
        raise HTTPException(status_code=404, detail=f"Table {table_name} not found")

    cols        = list((tbl_entry.columns_meta or {}).keys())
    where_parts = []
    params      = {}

    if filters:
        for col, val in filters.items():
            if col in cols and val:
                where_parts.append(f'LOWER("{col}") LIKE :filt_{col}')
                params[f'filt_{col}'] = f'%{val.lower()}%'

    if search and cols:
        search_parts = [f'LOWER(COALESCE("{c}", \'\')) LIKE :search' for c in cols[:8]]
        where_parts.append(f"({' OR '.join(search_parts)})")
        params['search'] = f'%{search.lower()}%'

    where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

    total = db.execute(
        text(f'SELECT COUNT(*) FROM "{table_name}" {where_clause}'),
        params,
    ).scalar() or 0

    col_str = ', '.join(f'"{c}"' for c in cols)
    rows_raw = db.execute(
        text(
            f'SELECT id, _uploaded_at, _uploaded_by, {col_str} '
            f'FROM "{table_name}" {where_clause} '
            f'ORDER BY _uploaded_at DESC '
            f'LIMIT :lim OFFSET :off'
        ),
        {**params, 'lim': limit, 'off': offset},
    ).fetchall()

    all_cols = ['id', '_uploaded_at', '_uploaded_by'] + cols
    rows = [dict(zip(all_cols, row)) for row in rows_raw]

    # Convert datetimes to strings
    for row in rows:
        for k, v in row.items():
            if hasattr(v, 'isoformat'):
                row[k] = v.isoformat()
            elif v is None:
                row[k] = ''

    return {"total": total, "rows": rows, "columns": cols}


def delete_table(db: Session, table_name: str) -> dict:
    """Drop a dynamic table and remove from registry."""
    entry = db.query(AssetTableRegistry).filter(
        AssetTableRegistry.table_name == table_name
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Table not found")

    try:
        db.execute(text(f'DROP TABLE IF EXISTS "{table_name}"'))
    except Exception as e:
        print(f"  [DynamicTable] Drop table error: {e}")

    db.delete(entry)
    db.commit()
    return {"message": f"Table '{entry.display_name}' deleted"}


def delete_all_tables(db: Session) -> dict:
    """Drop ALL dynamic tables and clear registry."""
    entries = db.query(AssetTableRegistry).all()
    count   = 0
    for entry in entries:
        try:
            db.execute(text(f'DROP TABLE IF EXISTS "{entry.table_name}"'))
            count += 1
        except Exception as e:
            print(f"  [DynamicTable] Drop error for {entry.table_name}: {e}")
    db.query(AssetTableRegistry).delete()
    db.commit()
    return {"message": f"Deleted {count} asset tables"}


def delete_rows(db: Session, table_name: str, row_ids: List[str]) -> dict:
    """Delete specific rows from a dynamic table."""
    entry = db.query(AssetTableRegistry).filter(
        AssetTableRegistry.table_name == table_name
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Table not found")

    deleted = 0
    for rid in row_ids:
        result = db.execute(
            text(f'DELETE FROM "{table_name}" WHERE id = :id'),
            {'id': rid},
        )
        deleted += result.rowcount

    # Update row count
    new_count = db.execute(
        text(f'SELECT COUNT(*) FROM "{table_name}"')
    ).scalar() or 0
    entry.row_count = new_count
    db.commit()

    return {"message": f"Deleted {deleted} rows", "remaining": new_count}


# ─────────────────────────────────────────────────────────────────────────────
# ROUTING HELPERS
# Used by chat_service.escalate_to_ticket
# ─────────────────────────────────────────────────────────────────────────────

def _build_where_clause(
    cols_meta: dict,
    collected_filters: Dict[str, str],
) -> tuple:
    """
    Build WHERE clause and params from collected filters for a table.

    Key fix: for roles with multiple columns (e.g. two identifier columns:
    server_id AND server_name), generates OR conditions across all columns
    with that role. This ensures a filter like "mysql-prod-ecom-01" matches
    server_name even if server_id was the first identifier column seen.
    """
    # Build role → [all columns with that role] map
    role_map_single = {}   # role -> first column (for return value compat)
    role_map_all    = {}   # role -> [all columns]
    for col, meta in cols_meta.items():
        role = meta.get("role", ROLE_OTHER)
        if role not in role_map_single:
            role_map_single[role] = col
        if role not in role_map_all:
            role_map_all[role] = []
        role_map_all[role].append(col)

    where_parts = []
    params      = {}
    i           = 0

    for filter_key, filter_val in collected_filters.items():
        if not filter_val:
            continue

        # Determine which columns to search
        if filter_key in cols_meta:
            # Direct column name match
            target_cols = [filter_key]
        else:
            # Role-based match — use ALL columns with this role
            target_cols = role_map_all.get(filter_key, [])

        if not target_cols:
            continue

        # If multiple columns share the role, use OR between them
        col_parts = []
        for col in target_cols:
            safe_key = f"f_{i}_{col.replace('-', '_')[:20]}"
            col_parts.append(f'LOWER(COALESCE("{col}", \'\')) LIKE :{safe_key}')
            params[safe_key] = f'%{filter_val.lower()}%'
            i += 1

        if len(col_parts) == 1:
            where_parts.append(col_parts[0])
        else:
            where_parts.append(f"({' OR '.join(col_parts)})")

    return where_parts, params, role_map_single


def count_matches(
    db: Session,
    collected_filters: Dict[str, str],
) -> int:
    """Count total matching rows across ALL tables for given filters."""
    tables = get_all_tables(db)
    total  = 0

    for tbl in tables:
        cols_meta   = tbl.columns_meta or {}
        where_parts, params, _ = _build_where_clause(cols_meta, collected_filters)
        if not where_parts:
            continue
        where_clause = "WHERE " + " AND ".join(where_parts)
        try:
            cnt = db.execute(
                text(f'SELECT COUNT(*) FROM "{tbl.table_name}" {where_clause}'),
                params,
            ).scalar() or 0
            total += cnt
        except Exception as e:
            print(f"  [DynamicTable] Count error on {tbl.table_name}: {e}")

    return total


def find_asset_owner(
    db: Session,
    collected_filters: Dict[str, str],
    require_unique: bool = False,
) -> Optional[Dict]:
    """
    Search ALL dynamic tables for an asset matching the collected filters.

    Args:
        require_unique: if True, only return a result when exactly 1 row
                        matches across ALL tables. Used by progressive_match
                        to determine if the match is truly confident.
    """
    tables = get_all_tables(db)
    candidates = []

    for tbl in tables:
        cols_meta = tbl.columns_meta or {}
        where_parts, params, role_map = _build_where_clause(cols_meta, collected_filters)

        if not where_parts:
            continue

        where_clause = "WHERE " + " AND ".join(where_parts)
        try:
            # Get count first
            cnt = db.execute(
                text(f'SELECT COUNT(*) FROM "{tbl.table_name}" {where_clause}'),
                params,
            ).scalar() or 0

            if cnt == 0:
                continue

            # Get the matching row(s)
            rows = db.execute(
                text(f'SELECT * FROM "{tbl.table_name}" {where_clause} LIMIT 5'),
                params,
            ).fetchall()

            inspector  = inspect(db.bind)
            table_cols = [c['name'] for c in inspector.get_columns(tbl.table_name)]

            for row in rows:
                row_dict = dict(zip(table_cols, row))
                candidates.append({
                    "table_name":    tbl.table_name,
                    "display_name":  tbl.display_name,
                    "row":           {k: str(v) if v else '' for k, v in row_dict.items()},
                    "contact_email": row_dict.get(role_map.get(ROLE_CONTACT, ''), '') or '',
                    "manager_email": row_dict.get(role_map.get(ROLE_MANAGER, ''), '') or '',
                    "director_email":row_dict.get(role_map.get(ROLE_DIRECTOR, ''), '') or '',
                    "ops_email":     row_dict.get(role_map.get(ROLE_OPS, ''), '') or '',
                    "identifier":    row_dict.get(role_map.get(ROLE_IDENTIFIER, ''), '') or '',
                    "environment":   row_dict.get(role_map.get(ROLE_ENVIRONMENT, ''), '') or '',
                    "team":          row_dict.get(role_map.get(ROLE_TEAM, ''), '') or '',
                    "total_matches": cnt,
                })

        except Exception as e:
            print(f"  [DynamicTable] Query error on {tbl.table_name}: {e}")
            continue

    if not candidates:
        return None

    total_matches = sum(c["total_matches"] for c in candidates)

    # If require_unique and more than 1 row matches, return None
    # so progressive_match knows to keep asking questions
    if require_unique and total_matches > 1:
        return None

    # Return best candidate — prefer ones with contact_email populated
    best = sorted(candidates, key=lambda c: (
        bool(c["contact_email"]),   # prefer rows with contact email
        c["total_matches"] == 1,    # prefer unique matches
    ), reverse=True)[0]

    best["total_matches"] = total_matches
    return best


def introspect_all_tables(
    db: Session,
    domain_hint: Optional[str] = None,
) -> dict:
    """
    Build a unified schema snapshot across ALL dynamic tables.
    Used by asset_identifier_service to generate questions.

    Returns:
    {
        "total_assets": 200,
        "tables": [{"name": "...", "display": "...", "rows": 84}],
        "columns": {
            "hostname":    {"distinct": 84, "samples": [...], "role": "identifier", "tables": ["dyn_..."]},
            "environment": {"distinct": 3,  "samples": [...], "role": "environment","tables": ["dyn_..."]},
        }
    }
    """
    tables = get_all_tables(db)
    if not tables:
        return {"total_assets": 0, "tables": [], "columns": {}}

    total_assets = 0
    table_info   = []
    all_columns: Dict[str, Dict] = {}

    for tbl in tables:
        try:
            count = db.execute(
                text(f'SELECT COUNT(*) FROM "{tbl.table_name}"')
            ).scalar() or 0
        except Exception:
            count = tbl.row_count

        total_assets += count
        table_info.append({
            "name":    tbl.table_name,
            "display": tbl.display_name,
            "rows":    count,
        })

        for col, meta in (tbl.columns_meta or {}).items():
            role = meta.get("role", ROLE_OTHER)
            # Skip ownership columns — they are answers not questions
            if role in (ROLE_CONTACT, ROLE_MANAGER, ROLE_DIRECTOR, ROLE_OPS):
                continue

            # Apply domain hint filter
            if domain_hint and domain_hint not in ("other", ""):
                if role not in (ROLE_IDENTIFIER, ROLE_ENVIRONMENT, ROLE_TEAM,
                                ROLE_REGION, ROLE_APP):
                    # Only include columns from tables matching the domain hint
                    tbl_matches = any(
                        domain_hint.lower() in str(s).lower()
                        for s in meta.get("samples", [])
                    )
                    if not tbl_matches:
                        continue

            if col not in all_columns:
                all_columns[col] = {
                    "distinct": meta.get("distinct", 0),
                    "samples":  meta.get("samples", []),
                    "role":     role,
                    "tables":   [tbl.table_name],
                }
            else:
                # Merge samples from multiple tables
                existing = all_columns[col]
                merged_samples = list(dict.fromkeys(
                    existing["samples"] + meta.get("samples", [])
                ))[:6]
                all_columns[col]["samples"]  = merged_samples
                all_columns[col]["distinct"] += meta.get("distinct", 0)
                if tbl.table_name not in existing["tables"]:
                    all_columns[col]["tables"].append(tbl.table_name)

    return {
        "total_assets": total_assets,
        "tables":       table_info,
        "columns":      all_columns,
    }