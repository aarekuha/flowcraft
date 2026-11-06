from sqlalchemy import BigInteger, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class UserOperationSkill(Base):
    __tablename__ = "user_operation_skills"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "operation_catalog_entry_id",
            name="uq_user_operation_skills_user_operation",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    operation_catalog_entry_id: Mapped[int] = mapped_column(
        ForeignKey("operation_catalog_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    user = relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="operation_skills",
    )
    operation_catalog_entry = relationship("OperationCatalogEntry", lazy="joined")
    created_by_user = relationship("User", foreign_keys=[created_by_user_id])
