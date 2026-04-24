from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPKMixin


class Agent(UUIDPKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "agents"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    retell_agent_override_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
