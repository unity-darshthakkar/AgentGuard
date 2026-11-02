"""add_paypal_order_status_and_nullable_order_id

Revision ID: 329a2a18ecd4
Revises: 070ff4e76b58
Create Date: 2026-10-31 13:56:10.384107

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '329a2a18ecd4'
down_revision: Union[str, None] = '070ff4e76b58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite doesn't support ALTER COLUMN for changing FK or NOT NULL directly
    # Need to recreate the table

    # 1. Create new table with updated schema
    op.create_table(
        'paypal_orders_new',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('auth_decision_id', sa.Integer(), nullable=False),
        sa.Column('reservation_id', sa.Integer(), nullable=False),
        sa.Column('paypal_order_id', sa.String(length=64), nullable=True),
        sa.Column('paypal_request_id', sa.String(length=108), nullable=False),
        sa.Column('amount_cents', sa.BigInteger(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='USD'),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='creating'),
        sa.Column('approval_url', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['auth_decision_id'], ['authorization_decisions.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['reservation_id'], ['authorization_reservations.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )

    # 2. Create indexes
    op.create_index(op.f('ix_paypal_orders_new_auth_decision_id'), 'paypal_orders_new', ['auth_decision_id'], unique=True)
    op.create_index(op.f('ix_paypal_orders_new_paypal_order_id'), 'paypal_orders_new', ['paypal_order_id'], unique=True)
    op.create_index(op.f('ix_paypal_orders_new_paypal_request_id'), 'paypal_orders_new', ['paypal_request_id'], unique=True)
    op.create_index(op.f('ix_paypal_orders_new_reservation_id'), 'paypal_orders_new', ['reservation_id'], unique=True)
    op.create_index(op.f('ix_paypal_orders_new_status'), 'paypal_orders_new', ['status'], unique=False)

    # 3. Copy data from old table (existing records become CREATED status)
    op.execute("""
        INSERT INTO paypal_orders_new (
            id, auth_decision_id, reservation_id, paypal_order_id, paypal_request_id,
            amount_cents, currency, status, approval_url, created_at, updated_at
        )
        SELECT
            id, auth_decision_id, reservation_id, paypal_order_id, paypal_request_id,
            amount_cents, currency, 'created', approval_url, created_at, updated_at
        FROM paypal_orders
    """)

    # 4. Drop old table and rename new
    op.drop_index(op.f('ix_paypal_orders_reservation_id'), table_name='paypal_orders')
    op.drop_index(op.f('ix_paypal_orders_paypal_request_id'), table_name='paypal_orders')
    op.drop_index(op.f('ix_paypal_orders_paypal_order_id'), table_name='paypal_orders')
    op.drop_index(op.f('ix_paypal_orders_auth_decision_id'), table_name='paypal_orders')
    op.drop_table('paypal_orders')

    op.rename_table('paypal_orders_new', 'paypal_orders')


def downgrade() -> None:
    # Reverse: recreate old table schema
    op.create_table(
        'paypal_orders_old',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('auth_decision_id', sa.Integer(), nullable=False),
        sa.Column('reservation_id', sa.Integer(), nullable=False),
        sa.Column('paypal_order_id', sa.String(length=64), nullable=False),
        sa.Column('paypal_request_id', sa.String(length=108), nullable=False),
        sa.Column('amount_cents', sa.BigInteger(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='USD'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='CREATED'),
        sa.Column('approval_url', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['auth_decision_id'], ['authorization_decisions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reservation_id'], ['authorization_reservations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_index(op.f('ix_paypal_orders_old_auth_decision_id'), 'paypal_orders_old', ['auth_decision_id'], unique=True)
    op.create_index(op.f('ix_paypal_orders_old_paypal_order_id'), 'paypal_orders_old', ['paypal_order_id'], unique=True)
    op.create_index(op.f('ix_paypal_orders_old_paypal_request_id'), 'paypal_orders_old', ['paypal_request_id'], unique=True)
    op.create_index(op.f('ix_paypal_orders_old_reservation_id'), 'paypal_orders_old', ['reservation_id'], unique=True)

    # Copy data back (only CREATED records, others would be lost in downgrade)
    op.execute("""
        INSERT INTO paypal_orders_old (
            id, auth_decision_id, reservation_id, paypal_order_id, paypal_request_id,
            amount_cents, currency, status, approval_url, created_at, updated_at
        )
        SELECT
            id, auth_decision_id, reservation_id, paypal_order_id, paypal_request_id,
            amount_cents, currency, status, approval_url, created_at, updated_at
        FROM paypal_orders
        WHERE status = 'created'
    """)

    op.drop_index(op.f('ix_paypal_orders_status'), table_name='paypal_orders')
    op.drop_index(op.f('ix_paypal_orders_reservation_id'), table_name='paypal_orders')
    op.drop_index(op.f('ix_paypal_orders_paypal_request_id'), table_name='paypal_orders')
    op.drop_index(op.f('ix_paypal_orders_paypal_order_id'), table_name='paypal_orders')
    op.drop_index(op.f('ix_paypal_orders_auth_decision_id'), table_name='paypal_orders')
    op.drop_table('paypal_orders')

    op.rename_table('paypal_orders_old', 'paypal_orders')
