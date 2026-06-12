"""add missing indexes for tickets, engineers, teams

Revision ID: 3a7c9f2e1b84
Revises: 0f2358fab959
Create Date: 2026-06-10
"""

from alembic import op

revision = "3a7c9f2e1b84"
down_revision = "0f2358fab959"
branch_labels = None
depends_on = None


def upgrade():
    # tickets.user_id — used in every "list my tickets" query
    op.create_index("ix_tickets_user_id", "tickets", ["user_id"])
    # tickets.status — used in analytics and dashboard queries
    op.create_index("ix_tickets_status", "tickets", ["status"])
    # engineers.is_activated — used in engineer availability lookups
    op.create_index("ix_engineers_is_activated", "engineers", ["is_activated"])
    # teams.is_active — used in team routing lookups
    op.create_index("ix_teams_is_active", "teams", ["is_active"])


def downgrade():
    op.drop_index("ix_teams_is_active",        table_name="teams")
    op.drop_index("ix_engineers_is_activated", table_name="engineers")
    op.drop_index("ix_tickets_status",         table_name="tickets")
    op.drop_index("ix_tickets_user_id",        table_name="tickets")
