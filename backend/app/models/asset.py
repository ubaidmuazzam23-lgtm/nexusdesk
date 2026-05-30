# Location: ./backend/app/models/asset.py
#
# CHANGES FROM ORIGINAL:
#   + Added `schema_meta` JSON column to store the semantic map generated
#     at CSV upload time. This tells the system which columns are identifiers
#     vs ownership fields, and what distinct values exist — so question
#     generation works even without a live DB query during chat.
#
#   All other columns are UNCHANGED from original.

from sqlalchemy import Column, String, Boolean, DateTime, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

from app.core.database import Base


class AssetRegistry(Base):
    __tablename__ = "asset_registry"

    id                              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── Account / Cloud ───────────────────────────────────────────────────────
    account_id                      = Column(String, nullable=True)
    account_name                    = Column(String, nullable=True)
    cloud_provider                  = Column(String, nullable=True)
    region                          = Column(String, nullable=True)
    availability_zone               = Column(String, nullable=True)

    # ── Instance / Network ────────────────────────────────────────────────────
    instance_name                   = Column(String, nullable=True, index=True)
    vpc_name                        = Column(String, nullable=True)
    vpc_id                          = Column(String, nullable=True)
    private_ip_address              = Column(String, nullable=True)
    public_ip_address               = Column(String, nullable=True)

    # ── Application ───────────────────────────────────────────────────────────
    application                     = Column(String, nullable=True, index=True)
    environment                     = Column(String, nullable=True, index=True)   # Prd / Stg / Dev
    team_verticals                  = Column(String, nullable=True)               # MySQL, Analytics, etc.

    # ── Team / Ownership ──────────────────────────────────────────────────────
    team                            = Column(String, nullable=True, index=True)
    contact_email                   = Column(String, nullable=True)
    engineering_dev_manager_email   = Column(String, nullable=True)
    engineering_dev_director_email  = Column(String, nullable=True)
    cloudops_manager_email          = Column(String, nullable=True)
    cloudops_director_email         = Column(String, nullable=True)

    # ── OS / State ────────────────────────────────────────────────────────────
    power_state                     = Column(String, nullable=True)
    os_details                      = Column(String, nullable=True)
    os_distribution                 = Column(String, nullable=True)
    is_active                       = Column(Boolean, default=True)

    # ── Schema metadata (NEW) ─────────────────────────────────────────────────
    # Populated at upload time by asset_service.upload_csv().
    # Stores the introspected schema snapshot so asset_identifier_service
    # can generate questions without re-scanning the entire table on every chat.
    #
    # Shape (stored on a sentinel row or a separate table; here stored on
    # each row for simplicity — only the first row's value is used):
    # {
    #   "total_assets": 2400,
    #   "columns": {
    #     "environment": {"distinct": 3, "samples": ["Prd","Stg","Dev"]},
    #     ...
    #   }
    # }
    #
    # NOTE: Run Alembic migration to add this column to existing deployments:
    #   ALTER TABLE asset_registry ADD COLUMN schema_meta JSONB;
    schema_meta                     = Column(JSON, nullable=True)

    # ── Meta ──────────────────────────────────────────────────────────────────
    uploaded_by                     = Column(String, nullable=True)
    created_at                      = Column(DateTime, default=datetime.utcnow)
    updated_at                      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Asset {self.instance_name} ({self.environment})>"