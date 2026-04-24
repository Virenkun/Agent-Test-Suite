from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPKMixin
from app.models.test_run import TestRunStatus


class TestSuite(UUIDPKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "test_suites"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    cases: Mapped[list["TestSuiteCase"]] = relationship(
        back_populates="test_suite",
        cascade="all, delete-orphan",
        order_by="TestSuiteCase.order_index",
    )
    runs: Mapped[list["TestSuiteRun"]] = relationship(back_populates="test_suite")


class TestSuiteCase(Base):
    __tablename__ = "test_suite_cases"

    test_suite_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("test_suites.id", ondelete="CASCADE"),
        primary_key=True,
    )
    test_case_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("test_cases.id", ondelete="CASCADE"),
        primary_key=True,
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    test_suite: Mapped["TestSuite"] = relationship(back_populates="cases")
    test_case = relationship("TestCase", lazy="joined")


class TestSuiteRun(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "test_suite_runs"
    __table_args__ = (
        Index("ix_test_suite_runs_suite_started", "test_suite_id", "started_at"),
    )

    test_suite_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("test_suites.id", ondelete="RESTRICT"),
        nullable=False,
    )
    agent_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
    )
    agent_phone_number: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[TestRunStatus] = mapped_column(
        Enum(
            TestRunStatus,
            name="test_run_status",
            create_type=False,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=TestRunStatus.PENDING,
    )
    calls_per_case: Mapped[int] = mapped_column(Integer, nullable=False)
    max_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    max_duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False, default=Decimal("0")
    )
    average_aggregate_score: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4), nullable=True
    )
    pass_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    test_suite: Mapped["TestSuite"] = relationship(back_populates="runs")
    test_runs = relationship(
        "TestRun", back_populates="test_suite_run", lazy="selectin"
    )
