"""add_paypal_captures_table

Revision ID: 0e8a5b9979f6
Revises: 329a2a18ecd4
Create Date: 2026-10-31 16:41:31.955268

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0e8a5b9979f6'
down_revision: Union[str, None] = '329a2a18ecd4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create paypal_captures table
    op.create_table(
        'paypal_captures',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('paypal_order_id', sa.Integer(), nullable=False),
        sa.Column('paypal_capture_id', sa.String(length=64), nullable=True),
        sa.Column('paypal_request_id', sa.String(length=108), nullable=False),
        sa.Column('amount_cents', sa.BigInteger(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('status', sa.Enum('capturing', 'completed', 'unknown', 'failed', name='paypalcapturestatus', native_enum=False), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['paypal_order_id'], ['paypal_orders.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_paypal_captures_paypal_capture_id'), 'paypal_captures', ['paypal_capture_id'], unique=True)
    op.create_index(op.f('ix_paypal_captures_paypal_order_id'), 'paypal_captures', ['paypal_order_id'], unique=True)
    op.create_index(op.f('ix_paypal_captures_paypal_request_id'), 'paypal_captures', ['paypal_request_id'], unique=True)
    op.create_index('ix_paypal_captures_request_id', 'paypal_captures', ['paypal_request_id'], unique=True)
    op.create_index(op.f('ix_paypal_captures_status'), 'paypal_captures', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_paypal_captures_status'), table_name='paypal_captures')
    op.drop_index('ix_paypal_captures_request_id', table_name='paypal_captures')
    op.drop_index(op.f('ix_paypal_captures_paypal_request_id'), table_name='paypal_captures')
    op.drop_index(op.f('ix_paypal_captures_paypal_order_id'), table_name='paypal_captures')
    op.drop_index(op.f('ix_paypal_captures_paypal_capture_id'), table_name='paypal_captures')
    op.drop_table('paypal_captures')