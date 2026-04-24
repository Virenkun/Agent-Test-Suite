"""phase 3 features: agents, test suites, suite runs, insights

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------- agents -------
    op.create_table(
        "agents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("phone_number", sa.String(32), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("retell_agent_override_id", sa.String(128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ux_agents_phone_active",
        "agents",
        ["phone_number"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ------- test_suites -------
    op.create_table(
        "test_suites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "test_suite_cases",
        sa.Column(
            "test_suite_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("test_suites.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "test_case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("test_cases.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("order_index", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_test_suite_cases_order",
        "test_suite_cases",
        ["test_suite_id", "order_index"],
    )

    # ------- test_suite_runs -------
    # Reuse the test_run_status enum from migration 0001.
    test_run_status = postgresql.ENUM(
        "pending",
        "running",
        "completed",
        "failed",
        "partial",
        name="test_run_status",
        create_type=False,
    )

    op.create_table(
        "test_suite_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "test_suite_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("test_suites.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("agent_phone_number", sa.String(32), nullable=False),
        sa.Column(
            "status",
            test_run_status,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("calls_per_case", sa.Integer, nullable=False),
        sa.Column("max_cost_usd", sa.Numeric(10, 4), nullable=True),
        sa.Column("max_duration_sec", sa.Integer, nullable=True),
        sa.Column(
            "total_cost_usd", sa.Numeric(10, 4), nullable=False, server_default="0"
        ),
        sa.Column("average_aggregate_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("pass_rate", sa.Numeric(5, 4), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_test_suite_runs_suite_started",
        "test_suite_runs",
        ["test_suite_id", "started_at"],
    )

    # ------- test_runs additions -------
    op.add_column(
        "test_runs",
        sa.Column(
            "test_suite_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("test_suite_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "test_runs",
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "test_runs",
        sa.Column("insights", postgresql.JSONB, nullable=True),
    )
    op.create_index(
        "ix_test_runs_suite_run_id", "test_runs", ["test_suite_run_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_test_runs_suite_run_id", table_name="test_runs")
    op.drop_column("test_runs", "insights")
    op.drop_column("test_runs", "agent_id")
    op.drop_column("test_runs", "test_suite_run_id")

    op.drop_index(
        "ix_test_suite_runs_suite_started", table_name="test_suite_runs"
    )
    op.drop_table("test_suite_runs")

    op.drop_index("ix_test_suite_cases_order", table_name="test_suite_cases")
    op.drop_table("test_suite_cases")
    op.drop_table("test_suites")

    op.drop_index("ux_agents_phone_active", table_name="agents")
    op.drop_table("agents")
