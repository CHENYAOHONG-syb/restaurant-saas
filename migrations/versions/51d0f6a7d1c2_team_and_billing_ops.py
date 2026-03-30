"""team and billing ops

Revision ID: 51d0f6a7d1c2
Revises: afde1e2733c9
Create Date: 2026-03-25 18:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "51d0f6a7d1c2"
down_revision = "afde1e2733c9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("subscriptions", sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("subscriptions", sa.Column("canceled_at", sa.DateTime(), nullable=True))

    op.create_table(
        "billing_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("summary", sa.String(length=255), nullable=True),
        sa.Column("provider_event_id", sa.String(length=120), nullable=True),
        sa.Column("amount_cents", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=12), nullable=True),
        sa.Column("reference_url", sa.String(length=255), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "team_invitations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=120), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("token", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("invited_by_user_id", sa.Integer(), nullable=True),
        sa.Column("accepted_user_id", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.ForeignKeyConstraint(["accepted_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
    )


def downgrade():
    op.drop_table("team_invitations")
    op.drop_table("billing_events")
    op.drop_column("subscriptions", "canceled_at")
    op.drop_column("subscriptions", "cancel_at_period_end")
