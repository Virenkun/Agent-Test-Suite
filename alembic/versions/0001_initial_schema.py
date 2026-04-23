"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "personas",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("tone", sa.String(200), nullable=True),
        sa.Column("personality", sa.Text, nullable=True),
        sa.Column("goal", sa.Text, nullable=True),
        sa.Column(
            "constraints",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("prompt_instructions", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "test_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "persona_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("personas.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("context", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    criterion_type = postgresql.ENUM(
        "boolean", "score", name="criterion_type", create_type=False
    )
    criterion_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "evaluation_criteria",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "test_case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("test_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("type", criterion_type, nullable=False),
        sa.Column("instructions", sa.Text, nullable=False),
        sa.Column("weight", sa.Numeric(10, 4), nullable=False, server_default="1.0"),
        sa.Column("max_score", sa.Integer, nullable=True),
        sa.Column("order_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_evaluation_criteria_test_case_id", "evaluation_criteria", ["test_case_id"])

    test_run_status = postgresql.ENUM(
        "pending",
        "running",
        "completed",
        "failed",
        "partial",
        name="test_run_status",
        create_type=False,
    )
    test_run_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "test_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "test_case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("test_cases.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "status",
            test_run_status,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("agent_phone_number", sa.String(32), nullable=False),
        sa.Column("requested_calls", sa.Integer, nullable=False),
        sa.Column("completed_calls", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failed_calls", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_cost_usd", sa.Numeric(10, 4), nullable=True),
        sa.Column("max_duration_sec", sa.Integer, nullable=True),
        sa.Column("total_cost_usd", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("aggregate_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("pass", sa.Boolean, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_test_runs_test_case_id", "test_runs", ["test_case_id"])
    op.create_index("ix_test_runs_test_case_started", "test_runs", ["test_case_id", "started_at"])

    call_status = postgresql.ENUM(
        "queued",
        "in_progress",
        "completed",
        "failed",
        "timeout",
        name="call_status",
        create_type=False,
    )
    call_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "test_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("test_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("retell_call_id", sa.String(128), nullable=True, unique=True),
        sa.Column(
            "status",
            call_status,
            nullable=False,
            server_default="queued",
        ),
        sa.Column("duration_sec", sa.Integer, nullable=True),
        sa.Column("transcript", sa.Text, nullable=True),
        sa.Column("recording_url", sa.String(1024), nullable=True),
        sa.Column("cost_usd", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_calls_retell_call_id", "calls", ["retell_call_id"])
    op.create_index("ix_calls_test_run_status", "calls", ["test_run_id", "status"])

    op.create_table(
        "call_evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "call_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("calls.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "criterion_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("evaluation_criteria.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("passed", sa.Boolean, nullable=True),
        sa.Column("score", sa.Numeric(10, 4), nullable=True),
        sa.Column("reasoning", sa.Text, nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("llm_cost_usd", sa.Numeric(10, 6), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("call_id", "criterion_id", name="uq_call_criterion"),
    )
    op.create_index("ix_call_evaluations_call_id", "call_evaluations", ["call_id"])


def downgrade() -> None:
    op.drop_index("ix_call_evaluations_call_id", table_name="call_evaluations")
    op.drop_table("call_evaluations")
    op.drop_index("ix_calls_test_run_status", table_name="calls")
    op.drop_index("ix_calls_retell_call_id", table_name="calls")
    op.drop_table("calls")
    op.execute("DROP TYPE IF EXISTS call_status")
    op.drop_index("ix_test_runs_test_case_started", table_name="test_runs")
    op.drop_index("ix_test_runs_test_case_id", table_name="test_runs")
    op.drop_table("test_runs")
    op.execute("DROP TYPE IF EXISTS test_run_status")
    op.drop_index("ix_evaluation_criteria_test_case_id", table_name="evaluation_criteria")
    op.drop_table("evaluation_criteria")
    op.execute("DROP TYPE IF EXISTS criterion_type")
    op.drop_table("test_cases")
    op.drop_table("personas")
