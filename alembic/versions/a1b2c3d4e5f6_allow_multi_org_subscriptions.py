"""Allow multi-org subscriptions

Remove unique constraint on subscriptions.user_id so a user can own
subscriptions for multiple organizations.  Add composite unique on
(user_id, organization_id) instead.

Revision ID: a1b2c3d4e5f6
Revises: ed50e31a4d49
Create Date: 2026-03-04
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "ed50e31a4d49"
branch_labels = None
depends_on = None


def _drop_unique_on_column(table: str, column: str) -> None:
    """Drop a unique constraint OR unique index on a single column.

    PostgreSQL constraint names vary depending on how they were created
    (e.g. via Alembic, raw SQL, or SQLAlchemy). SQLAlchemy's `unique=True`
    on a Column may create either a unique constraint or a unique index.
    This queries the catalog to find and drop whichever exists.
    """
    conn = op.get_bind()

    # First, try to find a unique CONSTRAINT
    result = conn.execute(
        sa.text("""
            SELECT con.conname
            FROM pg_constraint con
            JOIN pg_class rel ON rel.oid = con.conrelid
            JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
            WHERE rel.relname = :table
              AND con.contype = 'u'
              AND array_length(con.conkey, 1) = 1
              AND con.conkey[1] = (
                  SELECT attnum FROM pg_attribute
                  WHERE attrelid = rel.oid AND attname = :column
              )
        """),
        {"table": table, "column": column},
    )
    row = result.fetchone()
    if row:
        op.drop_constraint(row[0], table, type_="unique")
        return

    # Fallback: find a unique INDEX on the column
    result = conn.execute(
        sa.text("""
            SELECT i.relname
            FROM pg_index ix
            JOIN pg_class t ON t.oid = ix.indrelid
            JOIN pg_class i ON i.oid = ix.indexrelid
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
            WHERE t.relname = :table
              AND ix.indisunique = true
              AND ix.indisprimary = false
              AND array_length(ix.indkey, 1) = 1
              AND a.attname = :column
        """),
        {"table": table, "column": column},
    )
    row = result.fetchone()
    if row:
        op.drop_index(row[0], table_name=table)


def upgrade() -> None:
    # Dynamically find and drop the unique constraint/index on user_id
    # (name varies between environments / how it was originally created)
    _drop_unique_on_column("subscriptions", "user_id")

    # Add composite unique constraint: one subscription per user per org
    op.create_unique_constraint(
        "uq_subscription_user_org",
        "subscriptions",
        ["user_id", "organization_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_subscription_user_org", "subscriptions", type_="unique")
    op.create_unique_constraint("subscriptions_user_id_key", "subscriptions", ["user_id"])
