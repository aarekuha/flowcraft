from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.operation import Operation
from app.models.product import Product
from app.models.user import User
from app.schemas.product import (
    OperationCreate,
    OperationRead,
    ProductCreate,
    ProductDetail,
    ProductListItem,
)


class ProductService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_products(self) -> list[ProductListItem]:
        operations_count = (
            select(Operation.product_id, func.count(Operation.id).label("operations_count"))
            .group_by(Operation.product_id)
            .subquery()
        )

        stmt = (
            select(
                Product.id,
                Product.name,
                Product.version,
                Product.author,
                Product.author_user_id,
                Product.is_active,
                Product.created_at,
                func.coalesce(operations_count.c.operations_count, 0).label("operations_count"),
            )
            .outerjoin(operations_count, Product.id == operations_count.c.product_id)
            .order_by(Product.created_at.desc(), Product.id.desc())
        )

        rows = self.session.execute(stmt).all()
        return [self._build_list_item(row) for row in rows]

    def get_product(self, product_id: int) -> ProductDetail:
        product = self._get_product_or_404(product_id)
        return ProductDetail(
            id=product.id,
            name=product.name,
            version=product.version,
            author=product.author,
            author_user_id=product.author_user_id,
            is_active=product.is_active,
            created_at=product.created_at,
            operations=[self._serialize_operation(operation) for operation in product.operations],
        )

    def create_product(self, payload: ProductCreate) -> ProductDetail:
        self._validate_operation_names(payload.operations)
        self._validate_product_identity(name=payload.name, version=payload.version)
        author_user = self._resolve_product_author(payload.author_user_id)

        product = Product(
            name=payload.name,
            version=payload.version,
            author=author_user.name,
            author_user_id=author_user.id,
            is_active=True,
            created_at=int(datetime.now(UTC).timestamp() * 1000),
        )

        for index, operation in enumerate(payload.operations):
            product.operations.append(
                self._build_operation(
                    payload=operation,
                    sort_order=index,
                    product=product,
                )
            )

        self.session.add(product)
        self.session.commit()
        self.session.refresh(product)

        return self.get_product(product.id)

    def delete_product(self, product_id: int) -> None:
        product = self._get_product_or_404(product_id)
        self.session.delete(product)
        self.session.commit()

    def update_product_status(self, product_id: int, is_active: bool) -> ProductListItem:
        product = self._get_product_or_404(product_id)
        product.is_active = is_active
        self.session.commit()
        self.session.refresh(product)

        return ProductListItem(
            id=product.id,
            name=product.name,
            version=product.version,
            author=product.author,
            author_user_id=product.author_user_id,
            is_active=product.is_active,
            created_at=product.created_at,
            operations_count=self._count_operations(product.operations),
        )

    def _get_product_or_404(self, product_id: int) -> Product:
        stmt: Select[tuple[Product]] = (
            select(Product)
            .options(
                selectinload(Product.operations).selectinload(Operation.children),
            )
            .where(Product.id == product_id)
        )
        product = self.session.scalars(stmt).unique().one_or_none()
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {product_id} not found.",
            )
        return product

    def _build_operation(
        self,
        payload: OperationCreate,
        sort_order: int,
        product: Product,
    ) -> Operation:
        operation = Operation(
            name=payload.name,
            sort_order=sort_order,
            product=product,
        )

        for index, child in enumerate(payload.children):
            operation.children.append(
                self._build_operation(
                    payload=child,
                    sort_order=index,
                    product=product,
                )
            )

        return operation

    def _validate_operation_names(self, operations: Sequence[OperationCreate]) -> None:
        counts: dict[str, int] = {}

        for operation in operations:
            normalized = operation.name.strip().lower()
            counts[normalized] = counts.get(normalized, 0) + 1

        duplicates = [name for name, count in counts.items() if count > 1]
        if duplicates:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Operation names must be unique among siblings.",
            )

        for operation in operations:
            self._validate_operation_names(operation.children)

    def _validate_product_identity(self, name: str, version: str) -> None:
        stmt = select(Product.id).where(
            Product.name == name,
            Product.version == version,
        )
        existing_product_id = self.session.execute(stmt).scalar_one_or_none()

        if existing_product_id is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Product with this name and version already exists.",
            )

    def _serialize_operation(self, operation: Operation) -> OperationRead:
        ordered_children = sorted(operation.children, key=lambda item: item.sort_order)
        return OperationRead(
            id=operation.id,
            name=operation.name,
            children=[self._serialize_operation(child) for child in ordered_children],
        )

    def _count_operations(self, operations: Sequence[Operation]) -> int:
        return sum(1 + self._count_operations(operation.children) for operation in operations)

    def _build_list_item(self, row: Any) -> ProductListItem:
        return ProductListItem(
            id=row.id,
            name=row.name,
            version=row.version,
            author=row.author,
            author_user_id=row.author_user_id,
            is_active=row.is_active,
            created_at=row.created_at,
            operations_count=row.operations_count,
        )

    def _resolve_product_author(self, author_user_id: int | None) -> User:
        if author_user_id is not None:
            user = self.session.get(User, author_user_id)
            if user is None or user.deleted_at is not None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Author user not found.",
                )
            return user

        stmt = (
            select(User)
            .where(User.deleted_at.is_(None))
            .order_by(User.created_at.asc(), User.id.asc())
        )
        default_user = self.session.scalars(stmt).first()
        if default_user is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Create at least one user before creating products.",
            )
        return default_user
