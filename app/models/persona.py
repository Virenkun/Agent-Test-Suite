from typing import Any

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPKMixin


class Persona(UUIDPKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "personas"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    tone: Mapped[str | None] = mapped_column(String(200), nullable=True)
    personality: Mapped[str | None] = mapped_column(Text, nullable=True)
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    constraints: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    prompt_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)

    test_cases: Mapped[list["TestCase"]] = relationship(  # noqa: F821
        back_populates="persona"
    )
