import enum
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class CriterionType(str, enum.Enum):
    BOOLEAN = "boolean"
    SCORE = "score"


class EvaluationCriterion(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "evaluation_criteria"

    test_case_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("test_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[CriterionType] = mapped_column(
        Enum(
            CriterionType,
            name="criterion_type",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    weight: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False, default=Decimal("1.0")
    )
    max_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    test_case: Mapped["TestCase"] = relationship(back_populates="criteria")  # noqa: F821
    evaluations: Mapped[list["CallEvaluation"]] = relationship(  # noqa: F821
        back_populates="criterion"
    )
