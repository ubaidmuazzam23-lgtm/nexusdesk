# Location: backend/app/models/asset_table_registry.py
#
# PURPOSE:
#   Master registry that tracks every dynamic asset table created from CSV uploads.
#   Each row = one dynamic table in the database.
#
#   When an admin uploads a CSV:
#     1. System analyses columns + sample values
#     2. AI decides if it can merge with an existing table
#     3. If yes → appends rows to existing table, updates row_count
#     4. If no → creates new dynamic table, inserts a row here
#
#   The `columns_meta` JSON stores everything about the table structure:
#     - Original CSV column names
#     - Data type guess (email, ip, text, enum)
#     - Sample distinct values
#     - Semantic role (identifier / owner_email / manager_email / etc.)
#
#   Routing reads `columns_meta` to know which column to use for contact_email,
#   manager_email, etc. — no hardcoded column names anywhere.

from sqlalchemy import Column, String, Boolean, DateTime, Integer, JSON, Text
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

from app.core.database import Base


class AssetTableRegistry(Base):
    __tablename__ = "asset_table_registry"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── Table identity ────────────────────────────────────────────────────────
    # table_name: actual PostgreSQL table name  e.g. "dyn_asset_network_001"
    # display_name: human-readable name admin typed  e.g. "Network Assets"
    table_name   = Column(String, nullable=False, unique=True, index=True)
    display_name = Column(String, nullable=False)

    # ── Column metadata ───────────────────────────────────────────────────────
    # Shape:
    # {
    #   "hostname": {
    #     "original_name": "HOSTNAME",
    #     "samples": ["prod-web-01", "db-server-01"],
    #     "distinct": 84,
    #     "role": "identifier",          # identifier / contact_email / manager_email /
    #                                    # director_email / ops_email / environment /
    #                                    # team / region / ip / os / power_state / other
    #     "data_type": "text"            # text / email / ip / enum / integer
    #   },
    #   ...
    # }
    columns_meta = Column(JSON, nullable=False, default=dict)

    # ── Stats ─────────────────────────────────────────────────────────────────
    row_count    = Column(Integer, default=0)
    last_upload  = Column(DateTime, nullable=True)

    # ── State ─────────────────────────────────────────────────────────────────
    is_active    = Column(Boolean, default=True)
    uploaded_by  = Column(String, nullable=True)
    created_at   = Column(DateTime, default=datetime.utcnow)
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<AssetTable {self.display_name} ({self.table_name}) — {self.row_count} rows>"