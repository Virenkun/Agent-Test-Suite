from uuid import UUID

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPKMixin


class TestCase(UUIDPKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "test_cases"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    persona_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("personas.id", ondelete="RESTRICT"),
        nullable=False,
    )
    context: Mapped[str | None] = mapped_column(Text, nullable=True)

    persona: Mapped["Persona"] = relationship(back_populates="test_cases")  # noqa: F821
    criteria: Mapped[list["EvaluationCriterion"]] = relationship(  # noqa: F821
        back_populates="test_case",
        cascade="all, delete-orphan",
        order_by="EvaluationCriterion.order_index",
    )
    test_runs: Mapped[list["TestRun"]] = relationship(back_populates="test_case")  # noqa: F821
