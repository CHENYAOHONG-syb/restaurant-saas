"""inventory requirements and order flags

Revision ID: 9a5b8c3d1f42
Revises: 7c3f9a4d2b21
Create Date: 2026-03-26 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9a5b8c3d1f42"
down_revision = "7c3f9a4d2b21"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.add_column(sa.Column("inventory_applied_at", sa.DateTime(), nullable=True))

    op.create_table(
        "menu_inventory_requirements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("menu_id", sa.Integer(), nullable=False),
        sa.Column("inventory_item_id", sa.Integer(), nullable=False),
        sa.Column("quantity_required", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["inventory_item_id"], ["inventory_items.id"]),
        sa.ForeignKeyConstraint(["menu_id"], ["menu.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("menu_id", "inventory_item_id", name="uq_menu_inventory_requirement"),
    )


def downgrade():
    op.drop_table("menu_inventory_requirements")
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.drop_column("inventory_applied_at")
