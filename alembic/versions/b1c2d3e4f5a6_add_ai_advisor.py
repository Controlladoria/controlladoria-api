"""add_ai_advisor_conversations_and_plan_feature

Adds persistence for the AI financial advisor chat and enables the
`ai_advisor` feature flag on the Pro and Max plans.

Revision ID: b1c2d3e4f5a6
Revises: f8a9b0c1d2e3
Create Date: 2026-08-12

"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "f8a9b0c1d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Plans that include the advisor. Basic is explicitly set to False rather than
# left absent so the pricing page can render a clear "not included" row.
ADVISOR_PLANS = {"basic": False, "pro": True, "max": True}


def _set_advisor_feature(enabled_by_slug: dict) -> None:
    """
    Patch the `features` JSON on each plan.

    Done in Python rather than with a SQL JSON operator because the column is
    `JSON` (not `JSONB`) and the same migration has to run on both SQLite and
    PostgreSQL.
    """
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, slug, features FROM plans")
    ).fetchall()

    for row in rows:
        plan_id, slug, features = row[0], row[1], row[2]
        if slug not in enabled_by_slug:
            continue

        if isinstance(features, str):
            try:
                features = json.loads(features)
            except (TypeError, ValueError):
                features = {}
        if not isinstance(features, dict):
            features = {}

        features["ai_advisor"] = enabled_by_slug[slug]

        connection.execute(
            sa.text("UPDATE plans SET features = :features WHERE id = :id"),
            {"features": json.dumps(features), "id": plan_id},
        )


def _remove_advisor_feature() -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, features FROM plans")).fetchall()

    for row in rows:
        plan_id, features = row[0], row[1]
        if isinstance(features, str):
            try:
                features = json.loads(features)
            except (TypeError, ValueError):
                continue
        if not isinstance(features, dict) or "ai_advisor" not in features:
            continue

        features.pop("ai_advisor", None)
        connection.execute(
            sa.text("UPDATE plans SET features = :features WHERE id = :id"),
            {"features": json.dumps(features), "id": plan_id},
        )


def upgrade() -> None:
    op.create_table(
        "advisor_conversations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("summarized_through_id", sa.Integer(), nullable=True),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "is_archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_advisor_conversations_id", "advisor_conversations", ["id"]
    )
    op.create_index(
        "ix_advisor_conversations_organization_id",
        "advisor_conversations",
        ["organization_id"],
    )
    op.create_index(
        "ix_advisor_conversations_user_id", "advisor_conversations", ["user_id"]
    )
    # Backs the sidebar query: org's threads, most recent first.
    op.create_index(
        "ix_advisor_conv_org_updated",
        "advisor_conversations",
        ["organization_id", "updated_at"],
    )

    op.create_table(
        "advisor_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "conversation_id",
            sa.Integer(),
            sa.ForeignKey("advisor_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_advisor_messages_id", "advisor_messages", ["id"])
    op.create_index(
        "ix_advisor_messages_conversation_id", "advisor_messages", ["conversation_id"]
    )

    _set_advisor_feature(ADVISOR_PLANS)


def downgrade() -> None:
    _remove_advisor_feature()

    op.drop_index("ix_advisor_messages_conversation_id", table_name="advisor_messages")
    op.drop_index("ix_advisor_messages_id", table_name="advisor_messages")
    op.drop_table("advisor_messages")

    op.drop_index("ix_advisor_conv_org_updated", table_name="advisor_conversations")
    op.drop_index(
        "ix_advisor_conversations_user_id", table_name="advisor_conversations"
    )
    op.drop_index(
        "ix_advisor_conversations_organization_id", table_name="advisor_conversations"
    )
    op.drop_index("ix_advisor_conversations_id", table_name="advisor_conversations")
    op.drop_table("advisor_conversations")
