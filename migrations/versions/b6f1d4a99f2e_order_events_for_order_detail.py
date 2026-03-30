"""order events for order detail

Revision ID: b6f1d4a99f2e
Revises: 9a5b8c3d1f42
Create Date: 2026-03-26 18:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b6f1d4a99f2e"
down_revision = "9a5b8c3d1f42"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "order_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("from_status", sa.String(length=50), nullable=True),
        sa.Column("to_status", sa.String(length=50), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_order_events_order_id"), "order_events", ["order_id"], unique=False)
    op.create_index(op.f("ix_order_events_restaurant_id"), "order_events", ["restaurant_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_order_events_restaurant_id"), table_name="order_events")
    op.drop_index(op.f("ix_order_events_order_id"), table_name="order_events")
    op.drop_table("order_events")
