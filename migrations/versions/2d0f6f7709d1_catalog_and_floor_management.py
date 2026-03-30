"""catalog and floor management

Revision ID: 2d0f6f7709d1
Revises: 51d0f6a7d1c2
Create Date: 2026-03-26 10:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2d0f6f7709d1"
down_revision = "51d0f6a7d1c2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "inventory_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("stock", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=40), nullable=False),
        sa.Column("cost", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "menu_categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("restaurant_id", "name", name="uq_menu_categories_restaurant_name"),
    )

    with op.batch_alter_table("tables", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("status", sa.String(length=40), nullable=False, server_default="free")
        )
        batch_op.alter_column("table_number", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("restaurant_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_unique_constraint(
            "uq_tables_restaurant_table_number",
            ["restaurant_id", "table_number"],
        )


def downgrade():
    with op.batch_alter_table("tables", schema=None) as batch_op:
        batch_op.drop_constraint("uq_tables_restaurant_table_number", type_="unique")
        batch_op.alter_column("restaurant_id", existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column("table_number", existing_type=sa.Integer(), nullable=True)
        batch_op.drop_column("status")

    op.drop_table("menu_categories")
    op.drop_table("inventory_items")
