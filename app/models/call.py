import enum
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class CallStatus(str, enum.Enum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class Call(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "calls"
    __table_args__ = (
        Index("ix_calls_test_run_status", "test_run_id", "status"),
    )

    test_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("test_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    retell_call_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, unique=True, index=True
    )
    status: Mapped[CallStatus] = mapped_column(
        Enum(
            CallStatus,
            name="call_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=CallStatus.QUEUED,
    )
    duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    recording_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False, default=Decimal("0")
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    test_run: Mapped["TestRun"] = relationship(back_populates="calls")  # noqa: F821
    evaluations: Mapped[list["CallEvaluation"]] = relationship(  # noqa: F821
        back_populates="call", cascade="all, delete-orphan"
    )
