"""Create the foundational AgentGuard tables.

These tables are required by the Phase 2 credential and authorization
migration.  Keeping them in an explicit root revision makes a fresh database
portable across SQLite and PostgreSQL and removes the implicit create_all()
dependency from the migration path.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "000000000001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("agent_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.Enum("ACTIVE", "SUSPENDED", "PENDING_REVIEW", "DECOMMISSIONED", name="agentstatus", native_enum=False), nullable=False),
        sa.Column("owner_type", sa.String(length=32), nullable=False),
        sa.Column("owner_name", sa.String(length=128), nullable=False),
        sa.Column("owner_email", sa.String(length=256), nullable=False),
        sa.Column("owner_contact", sa.String(length=256), nullable=True),
        sa.Column("daily_limit_usd", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0"),
        sa.Column("monthly_limit_usd", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0"),
        sa.Column("allowed_merchant_categories", sa.Text(), nullable=True),
        sa.Column("blocked_merchant_categories", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("last_active_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id"),
    )
    op.create_index("ix_agents_agent_id", "agents", ["agent_id"], unique=True)
    op.create_index("ix_agents_status", "agents", ["status"], unique=False)
    op.create_index("ix_agents_status_created", "agents", ["status", "created_at"], unique=False)
    op.create_index("ix_agents_owner", "agents", ["owner_type", "owner_email"], unique=False)

    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("transaction_id", sa.String(length=64), nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=False),
        sa.Column("amount_usd", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("merchant_name", sa.String(length=128), nullable=False),
        sa.Column("merchant_category", sa.String(length=64), nullable=False),
        sa.Column("merchant_country", sa.String(length=2), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.Enum("APPROVED", "BLOCKED", "UNDER_REVIEW", "PENDING", "FAILED", name="transactionstatus", native_enum=False), nullable=False),
        sa.Column("risk_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("risk_level", sa.String(length=16), nullable=False, server_default="low"),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("transaction_id"),
    )
    op.create_index("ix_transactions_transaction_id", "transactions", ["transaction_id"], unique=True)
    op.create_index("ix_transactions_agent_id", "transactions", ["agent_id"], unique=False)
    op.create_index("ix_transactions_status", "transactions", ["status"], unique=False)
    op.create_index("ix_transactions_agent_status", "transactions", ["agent_id", "status"], unique=False)
    op.create_index("ix_transactions_requested", "transactions", ["requested_at"], unique=False)
    op.create_index("ix_transactions_risk", "transactions", ["risk_score", "risk_level"], unique=False)

    op.create_table(
        "security_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=False),
        sa.Column("transaction_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.Enum("VELOCITY_ANOMALY", "GEO_ANOMALY", "AMOUNT_OUTLIER", "NEW_MERCHANT", "PERMISSION_VIOLATION", "PATTERN_DEVIATION", name="securityeventtype", native_enum=False), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="info"),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("details_json", sa.Text(), nullable=True),
        sa.Column("detected_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
        sa.Column("acknowledged_by", sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index("ix_security_events_event_id", "security_events", ["event_id"], unique=True)
    op.create_index("ix_security_events_agent_id", "security_events", ["agent_id"], unique=False)
    op.create_index("ix_security_events_transaction_id", "security_events", ["transaction_id"], unique=False)
    op.create_index("ix_security_events_event_type", "security_events", ["event_type"], unique=False)
    op.create_index("ix_security_events_agent_type", "security_events", ["agent_id", "event_type"], unique=False)
    op.create_index("ix_security_events_detected", "security_events", ["detected_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_security_events_detected", table_name="security_events")
    op.drop_index("ix_security_events_agent_type", table_name="security_events")
    op.drop_index("ix_security_events_event_type", table_name="security_events")
    op.drop_index("ix_security_events_transaction_id", table_name="security_events")
    op.drop_index("ix_security_events_agent_id", table_name="security_events")
    op.drop_index("ix_security_events_event_id", table_name="security_events")
    op.drop_table("security_events")
    op.drop_index("ix_transactions_risk", table_name="transactions")
    op.drop_index("ix_transactions_requested", table_name="transactions")
    op.drop_index("ix_transactions_agent_status", table_name="transactions")
    op.drop_index("ix_transactions_status", table_name="transactions")
    op.drop_index("ix_transactions_agent_id", table_name="transactions")
    op.drop_index("ix_transactions_transaction_id", table_name="transactions")
    op.drop_table("transactions")
    op.drop_index("ix_agents_owner", table_name="agents")
    op.drop_index("ix_agents_status_created", table_name="agents")
    op.drop_index("ix_agents_status", table_name="agents")
    op.drop_index("ix_agents_agent_id", table_name="agents")
    op.drop_table("agents")
