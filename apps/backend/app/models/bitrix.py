# ruff: noqa: I001
from sqlalchemy import BigInteger, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BitrixConnection(Base):
    __tablename__ = "bitrix_connection"

    id: Mapped[int] = mapped_column(primary_key=True)
    portal: Mapped[str] = mapped_column(String(255))
    encrypted_webhook: Mapped[str] = mapped_column(Text)
    catalog_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    synced_at: Mapped[int | None] = mapped_column(BigInteger)
    job_id: Mapped[str | None] = mapped_column(String(36))
    started_at: Mapped[int | None] = mapped_column(BigInteger)
    last_error: Mapped[str | None] = mapped_column(String(500))
    job_kind: Mapped[str | None] = mapped_column(String(20))
    sync_progress: Mapped[dict | None] = mapped_column(JSON)
    deals_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    deals_synced_at: Mapped[int | None] = mapped_column(BigInteger)
    deals_last_error: Mapped[str | None] = mapped_column(String(500))


class BitrixProduct(Base):
    __tablename__ = "bitrix_products"

    id: Mapped[int] = mapped_column(primary_key=True)
    catalog_id: Mapped[int] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(default=True)
    present: Mapped[bool] = mapped_column(default=True)
    parent_id: Mapped[int | None]
    payload: Mapped[dict] = mapped_column(JSON)
    prices: Mapped[list] = mapped_column(JSON, default=list)


class BitrixMapping(Base):
    __tablename__ = "bitrix_mappings"

    bitrix_id: Mapped[int] = mapped_column(
        ForeignKey("bitrix_products.id"), primary_key=True
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )


class BitrixDeal(Base):
    __tablename__ = "bitrix_deals"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    category_id: Mapped[int] = mapped_column(index=True)
    stage_id: Mapped[str] = mapped_column(String(100))
    closed: Mapped[bool] = mapped_column(index=True)
    present: Mapped[bool] = mapped_column(default=True)
    payload: Mapped[dict] = mapped_column(JSON)
    product_rows: Mapped[list] = mapped_column(JSON)
    updated_at: Mapped[int] = mapped_column(BigInteger)
