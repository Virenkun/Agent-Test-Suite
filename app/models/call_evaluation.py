from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class CallEvaluation(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "call_evaluations"
    __table_args__ = (
        UniqueConstraint("call_id", "criterion_id", name="uq_call_criterion"),
    )

    call_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("calls.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    criterion_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("evaluation_criteria.id", ondelete="CASCADE"),
        nullable=False,
    )

    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    score: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    llm_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), nullable=False, default=Decimal("0")
    )

    call: Mapped["Call"] = relationship(back_populates="evaluations")  # noqa: F821
    criterion: Mapped["EvaluationCriterion"] = relationship(back_populates="evaluations")  # noqa: F821
