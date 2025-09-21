"""Add subscription plans and usage tracking for uploads."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "004_add_plans_and_subscriptions"
down_revision = "003_add_tenants_messages_usage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("max_projects", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "monthly_message_cap",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("2000"),
        ),
        sa.Column(
            "monthly_upload_char_cap",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("500000"),
        ),
        sa.Column(
            "is_annual_available",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )

    plan_table = sa.table(
        "plans",
        sa.column("id", sa.String()),
        sa.column("name", sa.String()),
        sa.column("max_projects", sa.Integer()),
        sa.column("monthly_message_cap", sa.Integer()),
        sa.column("monthly_upload_char_cap", sa.Integer()),
        sa.column("is_annual_available", sa.Boolean()),
    )

    op.bulk_insert(
        plan_table,
        [
            {
                "id": "hobby",
                "name": "Hobby",
                "max_projects": 1,
                "monthly_message_cap": 2000,
                "monthly_upload_char_cap": 500_000,
                "is_annual_available": True,
            },
            {
                "id": "pro",
                "name": "Pro",
                "max_projects": 5,
                "monthly_message_cap": 10000,
                "monthly_upload_char_cap": 2_000_000,
                "is_annual_available": True,
            },
            {
                "id": "business",
                "name": "Business",
                "max_projects": 20,
                "monthly_message_cap": 50000,
                "monthly_upload_char_cap": 10_000_000,
                "is_annual_available": True,
            },
        ],
    )

    op.create_table(
        "subscriptions",
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("plan_id", sa.String(), sa.ForeignKey("plans.id"), nullable=False),
        sa.Column("billing_cycle", sa.String(), nullable=False, server_default=sa.text("'monthly'")),
        sa.Column("current_period_start", sa.Date(), nullable=False, server_default=sa.func.current_date()),
        sa.Column("current_period_end", sa.Date(), nullable=False),
    )

    op.add_column(
        "usage_daily",
        sa.Column(
            "chars_uploaded",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("usage_daily", "chars_uploaded")
    op.drop_table("subscriptions")
    op.drop_table("plans")
