"""order and table status flow

Revision ID: 7c3f9a4d2b21
Revises: 2d0f6f7709d1
Create Date: 2026-03-26 12:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7c3f9a4d2b21"
down_revision = "2d0f6f7709d1"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE orders SET status = 'submitted' WHERE status = 'pending'")
    op.execute("UPDATE orders SET status = 'preparing' WHERE status = 'cooking'")
    op.execute("UPDATE orders SET status = 'paid' WHERE status = 'done'")
    op.execute("UPDATE tables SET status = 'available' WHERE status = 'free' OR status IS NULL")
    op.execute(
        """
        UPDATE tables
        SET status = 'occupied'
        WHERE EXISTS (
            SELECT 1
            FROM orders
            WHERE orders.restaurant_id = tables.restaurant_id
              AND orders.table_number = tables.table_number
              AND orders.status IN ('submitted', 'preparing', 'ready', 'served')
        )
        """
    )

    with op.batch_alter_table("tables", schema=None) as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=sa.String(length=40),
            server_default="available",
        )


def downgrade():
    op.execute("UPDATE orders SET status = 'pending' WHERE status = 'submitted'")
    op.execute("UPDATE orders SET status = 'cooking' WHERE status = 'preparing'")
    op.execute("UPDATE orders SET status = 'ready' WHERE status = 'served'")
    op.execute("UPDATE orders SET status = 'done' WHERE status = 'paid'")
    op.execute("UPDATE tables SET status = 'free' WHERE status = 'available'")

    with op.batch_alter_table("tables", schema=None) as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=sa.String(length=40),
            server_default="free",
        )
