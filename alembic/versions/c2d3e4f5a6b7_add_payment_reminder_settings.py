"""add_payment_reminder_settings

Per-user, per-company preferences for upcoming-payment reminders (email and
in-app).

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-09-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payment_reminder_settings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("email_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("in_app_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("frequency", sa.String(length=10), nullable=False, server_default="daily"),
        sa.Column("last_sent_period", sa.String(length=20), nullable=True),
        sa.Column("last_sent_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "organization_id", name="uq_payment_reminder_user_org"),
    )
    op.create_index("ix_payment_reminder_settings_id", "payment_reminder_settings", ["id"])
    op.create_index("ix_payment_reminder_settings_user_id", "payment_reminder_settings", ["user_id"])
    op.create_index(
        "ix_payment_reminder_settings_organization_id",
        "payment_reminder_settings",
        ["organization_id"],
    )
    # The daily job scans only opted-in rows.
    op.create_index("ix_payment_reminder_email_enabled", "payment_reminder_settings", ["email_enabled"])


def downgrade() -> None:
    op.drop_index("ix_payment_reminder_email_enabled", table_name="payment_reminder_settings")
    op.drop_index("ix_payment_reminder_settings_organization_id", table_name="payment_reminder_settings")
    op.drop_index("ix_payment_reminder_settings_user_id", table_name="payment_reminder_settings")
    op.drop_index("ix_payment_reminder_settings_id", table_name="payment_reminder_settings")
    op.drop_table("payment_reminder_settings")
