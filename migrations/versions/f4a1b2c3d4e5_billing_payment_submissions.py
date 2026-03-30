"""billing payment submissions

Revision ID: f4a1b2c3d4e5
Revises: c2e4d8b71a0f
Create Date: 2026-03-28 11:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f4a1b2c3d4e5"
down_revision = "c2e4d8b71a0f"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("billing_events", sa.Column("plan_key", sa.String(length=50), nullable=True))
    op.add_column("billing_events", sa.Column("payment_reference", sa.String(length=120), nullable=True))
    op.add_column("billing_events", sa.Column("attachment_path", sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column("billing_events", "attachment_path")
    op.drop_column("billing_events", "payment_reference")
    op.drop_column("billing_events", "plan_key")
