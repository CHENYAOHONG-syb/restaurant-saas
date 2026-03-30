"""order notes for order detail

Revision ID: c2e4d8b71a0f
Revises: b6f1d4a99f2e
Create Date: 2026-03-27 10:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c2e4d8b71a0f"
down_revision = "b6f1d4a99f2e"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("orders", sa.Column("note", sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column("orders", "note")
