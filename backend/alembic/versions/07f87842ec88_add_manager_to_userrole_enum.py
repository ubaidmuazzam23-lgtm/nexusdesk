# Location: ./backend/alembic/versions/07f87842ec88_add_manager_to_userrole_enum.py

"""add_manager_to_userrole_enum

Revision ID: 07f87842ec88
Revises: bee2bcfabc6b
Create Date: 2026-05-29 13:00:30.844437

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '07f87842ec88'
down_revision: Union[str, None] = 'bee2bcfabc6b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'manager'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values
    pass