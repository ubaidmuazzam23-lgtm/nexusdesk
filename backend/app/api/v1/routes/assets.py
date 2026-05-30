# Location: backend/app/api/v1/routes/assets.py
#
# REWRITTEN for dynamic multi-table asset registry.
# All endpoints now use dynamic_table_service instead of the old asset_service.

from fastapi import APIRouter, Depends, UploadFile, File, Form, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List

from app.core.database import get_db
from app.core.dependencies import require_role
from app.models.user import User, UserRole
from app.services.dynamic_table_service import (
    upload_asset_csv,
    get_all_tables,
    get_table_stats,
    query_table,
    delete_table,
    delete_all_tables,
    delete_rows,
    introspect_all_tables,
)

router = APIRouter(prefix="/assets", tags=["Assets"])


def get_admin(current_user: User = Depends(require_role(UserRole.ADMIN))) -> User:
    return current_user


# ── Upload ────────────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_asset_csv_endpoint(
    file:            UploadFile = File(...),
    display_name:    str        = Form(...),          # Admin gives the table a name
    force_new_table: bool       = Form(False),        # Skip merge check
    db:              Session    = Depends(get_db),
    admin:           User       = Depends(get_admin),
):
    """
    Upload a CSV file of assets.
    The system will:
      1. Parse any CSV structure
      2. Use AI to assign semantic roles to columns
      3. Decide if it can merge with an existing table
      4. Create new table or merge accordingly
    """
    if not file.filename.lower().endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files accepted")

    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Max 20MB.")
    if not content.strip():
        raise HTTPException(status_code=400, detail="File is empty")

    return upload_asset_csv(
        db             = db,
        content        = content,
        display_name   = display_name,
        uploaded_by    = str(admin.id),
        force_new_table= force_new_table,
    )


# ── List all tables ───────────────────────────────────────────────────────────

@router.get("/tables")
def list_tables(
    db:    Session = Depends(get_db),
    admin: User    = Depends(get_admin),
):
    """Return all asset tables with stats."""
    return get_table_stats(db)


# ── Schema intelligence ───────────────────────────────────────────────────────

@router.get("/schema")
def get_schema(
    domain: Optional[str] = Query(None),
    db:     Session        = Depends(get_db),
    admin:  User           = Depends(get_admin),
):
    """
    Return unified schema snapshot across all tables.
    Used by admin to verify question generation will work correctly.
    """
    schema = introspect_all_tables(db, domain_hint=domain)
    if schema["total_assets"] == 0:
        raise HTTPException(status_code=404, detail="No assets uploaded yet")
    return schema


# ── Query a specific table ────────────────────────────────────────────────────

@router.get("/table/{table_name}")
def get_table_rows(
    table_name: str,
    search:     Optional[str] = Query(None),
    limit:      int           = Query(500, le=2000),
    offset:     int           = Query(0),
    db:         Session       = Depends(get_db),
    admin:      User          = Depends(get_admin),
):
    """Query rows from a specific dynamic table with optional search."""
    return query_table(db, table_name, search=search, limit=limit, offset=offset)


# ── Delete ────────────────────────────────────────────────────────────────────

@router.delete("/all")
def delete_all(
    db:    Session = Depends(get_db),
    admin: User    = Depends(get_admin),
):
    """Drop ALL dynamic asset tables and clear the registry."""
    return delete_all_tables(db)


@router.delete("/table/{table_name}")
def delete_single_table(
    table_name: str,
    db:    Session = Depends(get_db),
    admin: User    = Depends(get_admin),
):
    """Drop a specific dynamic asset table."""
    return delete_table(db, table_name)


@router.delete("/table/{table_name}/rows")
def delete_table_rows(
    table_name: str,
    body: dict,
    db:    Session = Depends(get_db),
    admin: User    = Depends(get_admin),
):
    """Delete specific rows from a dynamic table."""
    row_ids = body.get("ids", [])
    if not row_ids:
        raise HTTPException(status_code=400, detail="No row IDs provided")
    return delete_rows(db, table_name, row_ids)