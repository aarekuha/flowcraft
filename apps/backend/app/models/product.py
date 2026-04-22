from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint, and_
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship

from app.core.database import Base
from app.models.operation import Operation
from app.models.user import User


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_products_name_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    author: Mapped[str] = mapped_column(String(255), nullable=False)
    author_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)

    author_user = relationship(User, lazy="joined")

    operations = relationship(
        Operation,
        back_populates="product",
        cascade="all, delete-orphan",
        order_by=Operation.sort_order,
        primaryjoin=lambda: and_(
            Product.id == foreign(Operation.product_id),
            Operation.parent_id.is_(None),
        ),
    )
