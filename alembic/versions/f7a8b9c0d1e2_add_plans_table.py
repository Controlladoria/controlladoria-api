"""add_plans_table

Revision ID: f7a8b9c0d1e2
Revises: e6b2c4d5f6a7
Create Date: 2026-03-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7a8b9c0d1e2'
down_revision: Union[str, None] = 'e6b2c4d5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create plans table
    plans_table = op.create_table(
        'plans',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('slug', sa.String(length=50), nullable=False),
        sa.Column('display_name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('max_users', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('price_monthly_brl', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('stripe_price_id', sa.String(length=255), nullable=True),
        sa.Column('features', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('is_highlighted', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_plans_slug', 'plans', ['slug'], unique=True)
    op.create_index('ix_plans_stripe_price_id', 'plans', ['stripe_price_id'], unique=True)
    op.create_index('ix_plans_id', 'plans', ['id'])

    # 2. Seed initial plans
    op.bulk_insert(plans_table, [
        {
            'id': 1,
            'slug': 'basic',
            'display_name': 'Básico',
            'description': 'Ideal para profissionais autônomos',
            'max_users': 1,
            'price_monthly_brl': 99,
            'stripe_price_id': None,
            'features': {
                'cash_flow_direct': False,
                'team_management': False,
                'api_access': False,
                'priority_support': False,
            },
            'is_active': True,
            'sort_order': 0,
            'is_default': True,
            'is_highlighted': False,
        },
        {
            'id': 2,
            'slug': 'pro',
            'display_name': 'Pro',
            'description': 'Para pequenas equipes contábeis',
            'max_users': 3,
            'price_monthly_brl': 249,
            'stripe_price_id': None,
            'features': {
                'cash_flow_direct': True,
                'team_management': True,
                'api_access': False,
                'priority_support': True,
            },
            'is_active': True,
            'sort_order': 1,
            'is_default': False,
            'is_highlighted': True,
        },
        {
            'id': 3,
            'slug': 'max',
            'display_name': 'Max',
            'description': 'Para escritórios e empresas maiores',
            'max_users': 5,
            'price_monthly_brl': 399,
            'stripe_price_id': None,
            'features': {
                'cash_flow_direct': True,
                'team_management': True,
                'api_access': True,
                'priority_support': True,
            },
            'is_active': True,
            'sort_order': 2,
            'is_default': False,
            'is_highlighted': False,
        },
    ])

    # 3. Add plan_id column to subscriptions
    op.add_column('subscriptions', sa.Column('plan_id', sa.Integer(), sa.ForeignKey('plans.id'), nullable=True))
    op.create_index('ix_subscriptions_plan_id', 'subscriptions', ['plan_id'])

    # 4. Backfill plan_id from max_users
    # max_users=1 → basic (id=1), max_users=3 → pro (id=2), max_users=5 → max (id=3)
    op.execute("UPDATE subscriptions SET plan_id = 1 WHERE max_users = 1 OR max_users IS NULL")
    op.execute("UPDATE subscriptions SET plan_id = 2 WHERE max_users = 3")
    op.execute("UPDATE subscriptions SET plan_id = 3 WHERE max_users = 5")
    # Catch-all for any unexpected values
    op.execute("UPDATE subscriptions SET plan_id = 1 WHERE plan_id IS NULL")


def downgrade() -> None:
    op.drop_index('ix_subscriptions_plan_id', table_name='subscriptions')
    op.drop_column('subscriptions', 'plan_id')
    op.drop_index('ix_plans_id', table_name='plans')
    op.drop_index('ix_plans_stripe_price_id', table_name='plans')
    op.drop_index('ix_plans_slug', table_name='plans')
    op.drop_table('plans')
