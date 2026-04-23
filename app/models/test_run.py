import enum
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class TestRunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class TestRun(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "test_runs"
    __table_args__ = (
        Index("ix_test_runs_test_case_started", "test_case_id", "started_at"),
    )

    test_case_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("test_cases.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[TestRunStatus] = mapped_column(
        Enum(
            TestRunStatus,
            name="test_run_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=TestRunStatus.PENDING,
    )
    agent_phone_number: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_calls: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    max_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    max_duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)

    total_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False, default=Decimal("0")
    )
    aggregate_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    pass_: Mapped[bool | None] = mapped_column("pass", Boolean, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    test_case: Mapped["TestCase"] = relationship(back_populates="test_runs")  # noqa: F821
    calls: Mapped[list["Call"]] = relationship(  # noqa: F821
        back_populates="test_run", cascade="all, delete-orphan"
    )
