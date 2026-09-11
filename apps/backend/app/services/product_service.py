from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.operation import Operation
from app.models.operation_catalog import OperationCatalogEntry
from app.models.product import Product
from app.models.user import User
from app.schemas.product import (
    OperationCostUpdate,
    OperationCreate,
    OperationRead,
    ProductCostsUpdate,
    ProductCreate,
    ProductDetail,
    ProductListItem,
)


class ProductService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_products(self) -> list[ProductListItem]:
        operations_count = (
            select(
                Operation.product_id,
                func.count(Operation.id).label("operations_count"),
            )
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
                Product.material_cost_cents,
                Product.is_active,
                Product.created_at,
                func.coalesce(operations_count.c.operations_count, 0).label(
                    "operations_count"
                ),
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
            material_cost_cents=product.material_cost_cents,
            is_active=product.is_active,
            created_at=product.created_at,
            operations=[
                self._serialize_operation(operation) for operation in product.operations
            ],
        )

    def create_product(self, payload: ProductCreate) -> ProductDetail:
        self._validate_group_operations(payload.operations)
        resolved_entries = self._resolve_operation_catalog_entries(payload.operations)
        self._validate_operation_catalog_entries_unique(
            payload.operations,
            resolved_entries,
        )
        self._validate_product_identity(name=payload.name, version=payload.version)
        author_user = self._resolve_product_author(payload.author_user_id)

        product = Product(
            name=payload.name,
            version=payload.version,
            author=author_user.name,
            author_user_id=author_user.id,
            material_cost_cents=payload.material_cost_cents,
            is_active=True,
            created_at=int(datetime.now(UTC).timestamp() * 1000),
        )

        for index, operation in enumerate(payload.operations):
            product.operations.append(
                self._build_operation(
                    payload=operation,
                    sort_order=index,
                    product=product,
                    resolved_entries=resolved_entries,
                )
            )

        self.session.add(product)
        self.session.commit()
        self.session.refresh(product)

        return self.get_product(product.id)

    def update_product_costs(
        self,
        product_id: int,
        payload: ProductCostsUpdate,
    ) -> ProductDetail:
        product = self._get_product_or_404(product_id)
        requested_operation_costs = self._collect_operation_costs(payload.operations)
        operations = self.session.scalars(
            select(Operation).where(Operation.product_id == product.id)
        ).all()
        operations_by_id = {operation.id: operation for operation in operations}

        unknown_operation_ids = set(requested_operation_costs) - set(operations_by_id)
        if unknown_operation_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Operation prices must reference existing product operations.",
            )

        for operation_id, requested_costs in requested_operation_costs.items():
            operation = operations_by_id[operation_id]
            current_price_cents = None if operation.children else operation.price_cents
            current_standard_time_seconds = (
                None if operation.children else operation.standard_time_seconds
            )
            if requested_costs[0] != current_price_cents:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Operation prices cannot be changed after product creation.",
                )
            if requested_costs[1] != current_standard_time_seconds:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=(
                        "Operation standard times cannot be changed after product "
                        "creation."
                    ),
                )

        product.material_cost_cents = payload.material_cost_cents

        self.session.commit()
        self.session.refresh(product)
        return self.get_product(product.id)

    def delete_product(self, product_id: int) -> None:
        product = self._get_product_or_404(product_id)
        self.session.delete(product)
        self.session.commit()

    def update_product_status(
        self,
        product_id: int,
        is_active: bool,
    ) -> ProductListItem:
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
            material_cost_cents=product.material_cost_cents,
            is_active=product.is_active,
            created_at=product.created_at,
            operations_count=self._count_operations(product.operations),
        )

    def _get_product_or_404(self, product_id: int) -> Product:
        stmt: Select[tuple[Product]] = (
            select(Product)
            .options(
                selectinload(Product.operations).selectinload(Operation.children),
                selectinload(Product.operations).selectinload(Operation.catalog_entry),
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
        resolved_entries: dict[int, OperationCatalogEntry],
    ) -> Operation:
        is_group = bool(payload.children)
        catalog_entry = None if is_group else resolved_entries[id(payload)]
        operation_name = payload.name or ""
        if catalog_entry is not None:
            operation_name = catalog_entry.name
        operation = Operation(
            operation_catalog_entry_id=(
                None if catalog_entry is None else catalog_entry.id
            ),
            name=operation_name,
            price_cents=payload.price_cents if not is_group else None,
            standard_time_seconds=(
                payload.standard_time_seconds if not is_group else None
            ),
            sort_order=sort_order,
            product=product,
        )

        for index, child in enumerate(payload.children):
            operation.children.append(
                self._build_operation(
                    payload=child,
                    sort_order=index,
                    product=product,
                    resolved_entries=resolved_entries,
                )
            )

        return operation

    def _validate_group_operations(
        self,
        operations: Sequence[OperationCreate],
    ) -> None:
        for operation in operations:
            if operation.children:
                if operation.price_cents is not None:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail="Operation groups cannot have prices.",
                    )
                if operation.standard_time_seconds is not None:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail="Operation groups cannot have standard times.",
                    )
                if operation.operation_catalog_entry_id is not None:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail=(
                            "Operation groups must not reference the operation "
                            "catalog."
                        ),
                    )
            self._validate_group_operations(operation.children)

    def _resolve_operation_catalog_entries(
        self,
        operations: Sequence[OperationCreate],
    ) -> dict[int, OperationCatalogEntry]:
        if not operations:
            return {}

        active_entries = self.session.scalars(
            select(OperationCatalogEntry).where(
                OperationCatalogEntry.is_active.is_(True)
            )
        ).all()
        active_entries_by_id = {entry.id: entry for entry in active_entries}
        active_entries_by_name = {
            self._normalize_search(entry.name): entry for entry in active_entries
        }
        resolved_entries: dict[int, OperationCatalogEntry] = {}

        def walk(nodes: Sequence[OperationCreate]) -> None:
            for operation in nodes:
                if operation.children:
                    walk(operation.children)
                    continue

                entry = self._resolve_operation_catalog_entry(
                    operation,
                    active_entries_by_id,
                    active_entries_by_name,
                )
                resolved_entries[id(operation)] = entry

        walk(operations)
        return resolved_entries

    def _resolve_operation_catalog_entry(
        self,
        operation: OperationCreate,
        active_entries_by_id: dict[int, OperationCatalogEntry],
        active_entries_by_name: dict[str, OperationCatalogEntry],
    ) -> OperationCatalogEntry:
        entry: OperationCatalogEntry | None = None
        if operation.operation_catalog_entry_id is not None:
            entry = active_entries_by_id.get(operation.operation_catalog_entry_id)
            if (
                entry is not None
                and operation.name is not None
                and self._normalize_search(entry.name)
                != self._normalize_search(operation.name)
            ):
                entry = None
        elif operation.name is not None:
            entry = active_entries_by_name.get(self._normalize_search(operation.name))

        if entry is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Operations must be selected from the operation catalog.",
            )

        return entry

    def _validate_operation_catalog_entries_unique(
        self,
        operations: Sequence[OperationCreate],
        resolved_entries: dict[int, OperationCatalogEntry],
    ) -> None:
        seen_entry_ids: set[int] = set()

        def walk(nodes: Sequence[OperationCreate]) -> None:
            for operation in nodes:
                if operation.children:
                    walk(operation.children)
                    continue

                entry = resolved_entries[id(operation)]
                if entry.id in seen_entry_ids:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail="Operations must be unique within a product.",
                    )
                seen_entry_ids.add(entry.id)

        walk(operations)

    def _validate_product_identity(self, name: str, version: str) -> None:
        stmt = select(Product.id).where(
            Product.name == name,
            Product.version == version,
        )
        existing_product_id = self.session.execute(stmt).scalar_one_or_none()

        if existing_product_id is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Product with this name and version already exists.",
            )

    def _collect_operation_costs(
        self,
        operations: Sequence[OperationCostUpdate],
    ) -> dict[int, tuple[int | None, int | None]]:
        costs: dict[int, tuple[int | None, int | None]] = {}

        def walk(nodes: Sequence[OperationCostUpdate]) -> None:
            for operation in nodes:
                if operation.id in costs:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail=(
                            "Operation prices must reference each operation only once."
                        ),
                    )

                costs[operation.id] = (
                    operation.price_cents,
                    operation.standard_time_seconds,
                )
                walk(operation.children)

        walk(operations)
        return costs

    def _serialize_operation(self, operation: Operation) -> OperationRead:
        ordered_children = sorted(operation.children, key=lambda item: item.sort_order)
        return OperationRead(
            id=operation.id,
            operation_catalog_entry_id=operation.operation_catalog_entry_id,
            name=self._get_operation_name(operation),
            price_cents=None if ordered_children else operation.price_cents,
            standard_time_seconds=(
                None if ordered_children else operation.standard_time_seconds
            ),
            children=[self._serialize_operation(child) for child in ordered_children],
        )

    def _count_operations(self, operations: Sequence[Operation]) -> int:
        return sum(
            1 + self._count_operations(operation.children) for operation in operations
        )

    def _build_list_item(self, row: Any) -> ProductListItem:
        return ProductListItem(
            id=row.id,
            name=row.name,
            version=row.version,
            author=row.author,
            author_user_id=row.author_user_id,
            material_cost_cents=row.material_cost_cents,
            is_active=row.is_active,
            created_at=row.created_at,
            operations_count=row.operations_count,
        )

    def _resolve_product_author(self, author_user_id: int | None) -> User:
        if author_user_id is not None:
            user = self.session.get(User, author_user_id)
            if user is None or user.deleted_at is not None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Create at least one user before creating products.",
            )
        return default_user

    def _normalize_search(self, value: str) -> str:
        return value.strip().casefold()

    def _get_operation_name(self, operation: Operation) -> str:
        if operation.catalog_entry is not None:
            return operation.catalog_entry.name
        return operation.name
