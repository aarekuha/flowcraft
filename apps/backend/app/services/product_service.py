# ruff: noqa: I001
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.operation import Operation
from app.models.operation_catalog import OperationCatalogEntry
from app.models.product import Product
from app.models.user import User
from app.models.work_order import WorkOrder
from app.schemas.operation_catalog import OperationCatalogEntryKind
from app.schemas.product import (
    OperationCostUpdate,
    OperationCreate,
    OperationRead,
    ProductCostsUpdate,
    ProductCreate,
    ProductDetail,
    ProductListItem,
    ProductStagesUpdate,
)
from app.services.operation_time_estimate_service import (
    OperationTimeEstimateService,
)
from app.services.planning_revision_service import PlanningRevisionService


from app.services.operation_pricing import recalculate_prices, get_base_rate


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
                Product.stage_count,
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
            base_rate_cents=get_base_rate(self.session),
            id=product.id,
            name=product.name,
            version=product.version,
            comment=product.comment,
            author=product.author,
            author_user_id=product.author_user_id,
            material_cost_cents=product.material_cost_cents,
            stage_count=product.stage_count,
            is_active=product.is_active,
            created_at=product.created_at,
            operations=[
                self._serialize_operation(operation) for operation in product.operations
            ],
        )

    def create_product(self, payload: ProductCreate) -> ProductDetail:
        self._validate_group_operations(payload.operations)
        resolved_entries = self._resolve_operation_catalog_entries(
            payload.operations,
            source_product_id=payload.source_product_id,
        )
        self._validate_operation_catalog_entries_unique(
            payload.operations,
            resolved_entries,
        )
        self._validate_created_operation_stages(
            payload.operations,
            resolved_entries,
            payload.stage_count,
        )
        self._validate_product_identity(name=payload.name, version=payload.version)
        author_user = self._resolve_product_author(payload.author_user_id)

        product = Product(
            name=payload.name,
            version=payload.version,
            comment=payload.comment,
            author=author_user.name,
            author_user_id=author_user.id,
            material_cost_cents=payload.material_cost_cents,
            stage_count=payload.stage_count,
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
        self.session.flush()
        OperationTimeEstimateService(self.session).mark_operations_dirty(
            {
                operation.id
                for operation in self._walk_operations(product.operations)
                if not operation.children
            },
            dirty_at=product.created_at,
        )
        recalculate_prices(
            self.session,
            {operation.id for operation in self._walk_operations(product.operations)},
        )
        self.session.commit()
        self.session.refresh(product)

        return self.get_product(product.id)

    def update_product_stages(
        self,
        product_id: int,
        payload: ProductStagesUpdate,
    ) -> ProductDetail:
        product = self._get_product_or_404(product_id)
        operations = self.session.scalars(
            select(Operation).where(Operation.product_id == product.id)
        ).all()
        parent_operation_ids = {
            operation.parent_id
            for operation in operations
            if operation.parent_id is not None
        }
        leaf_operations = {
            operation.id: operation
            for operation in operations
            if operation.id not in parent_operation_ids
        }
        requested_ids = [item.operation_id for item in payload.operations]
        requested_id_set = set(requested_ids)
        if len(requested_ids) != len(requested_id_set):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Каждая операция должна встречаться в схеме этапов один раз.",
            )
        if requested_id_set != set(leaf_operations):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    "Схема этапов должна содержать все конечные операции изделия "
                    "и не должна содержать группы."
                ),
            )

        for requested_stage in payload.operations:
            operation = leaf_operations[requested_stage.operation_id]
            self._validate_stage_range(
                stage_start=requested_stage.stage_start,
                stage_end=requested_stage.stage_end,
                stage_count=payload.stage_count,
                operation_kind=(
                    operation.catalog_entry.operation_kind
                    if operation.catalog_entry is not None
                    else None
                ),
            )

        for requested_stage in payload.operations:
            operation = leaf_operations[requested_stage.operation_id]
            operation.stage_start = requested_stage.stage_start
            operation.stage_end = requested_stage.stage_end

        product.stage_count = payload.stage_count
        PlanningRevisionService(self.session).request_recalculation()
        self.session.commit()
        self.session.refresh(product)
        return self.get_product(product.id)

    def update_product_costs(
        self,
        product_id: int,
        payload: ProductCostsUpdate,
        *,
        can_change_prices: bool = False,
    ) -> ProductDetail:
        product = self._get_product_or_404(product_id)
        requested_operation_updates = self._collect_operation_costs(payload.operations)
        operations = self.session.scalars(
            select(Operation).where(Operation.product_id == product.id)
        ).all()
        operations_by_id = {operation.id: operation for operation in operations}
        parent_operation_ids = {
            operation.parent_id
            for operation in operations
            if operation.parent_id is not None
        }

        unknown_operation_ids = set(requested_operation_updates) - set(operations_by_id)
        if unknown_operation_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Operation prices must reference existing product operations.",
            )

        standard_times_changed = False
        for operation_id, requested_update in requested_operation_updates.items():
            operation = operations_by_id[operation_id]
            is_group = operation.id in parent_operation_ids
            if (
                "price_cents" in requested_update.model_fields_set
                and requested_update.price_cents != operation.price_cents
            ):
                raise HTTPException(
                    422,
                    "Цена рассчитывается автоматически. Изменять коэффициент операции",
                )
            if (
                "coefficient_units" in requested_update.model_fields_set
                and requested_update.coefficient_units != operation.coefficient_units
            ):
                if not can_change_prices:
                    raise HTTPException(
                        403, "Изменение коэффициента доступно только администратору"
                    )
                if is_group:
                    raise HTTPException(
                        422, "Коэффициент можно задавать только операциям"
                    )
                operation.coefficient_units = requested_update.coefficient_units
            if "standard_time_seconds" not in requested_update.model_fields_set:
                continue
            if is_group:
                if requested_update.standard_time_seconds is not None:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail="Operation groups cannot have standard times.",
                    )
                continue
            if (
                requested_update.standard_time_seconds
                != operation.standard_time_seconds
            ):
                operation.standard_time_seconds = requested_update.standard_time_seconds
                standard_times_changed = True

        if standard_times_changed:
            PlanningRevisionService(self.session).request_recalculation()

        product.material_cost_cents = payload.material_cost_cents
        if "comment" in payload.model_fields_set:
            product.comment = payload.comment

        recalculate_prices(self.session, set(operations_by_id))
        self.session.commit()
        self.session.refresh(product)
        return self.get_product(product.id)

    def delete_product(self, product_id: int) -> None:
        product = self._get_product_or_404(product_id)
        if (
            self.session.scalar(
                select(WorkOrder.id).where(WorkOrder.product_id == product.id).limit(1)
            )
            is not None
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Нельзя удалить изделие, которое уже используется в заказах. "
                    "Изделие можно деактивировать."
                ),
            )
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
            stage_count=product.stage_count,
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
            coefficient_units=payload.coefficient_units,
            price_cents=0 if not is_group else None,
            standard_time_seconds=(
                payload.standard_time_seconds if not is_group else None
            ),
            stage_start=payload.stage_start if not is_group else 1,
            stage_end=payload.stage_end if not is_group else 1,
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
                            "Operation groups must not reference the operation catalog."
                        ),
                    )
            self._validate_group_operations(operation.children)

    def _resolve_operation_catalog_entries(
        self,
        operations: Sequence[OperationCreate],
        *,
        source_product_id: int | None,
    ) -> dict[int, OperationCatalogEntry]:
        permitted_inactive_entry_ids: set[int] = set()
        if source_product_id is not None:
            source_product_exists = self.session.scalar(
                select(Product.id).where(Product.id == source_product_id)
            )
            if source_product_exists is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Source product not found.",
                )
            source_entry_ids = self.session.scalars(
                select(Operation.operation_catalog_entry_id).where(
                    Operation.product_id == source_product_id,
                    Operation.operation_catalog_entry_id.is_not(None),
                )
            ).all()
            permitted_inactive_entry_ids = {
                entry_id for entry_id in source_entry_ids if entry_id is not None
            }

        if not operations:
            return {}

        entries = self.session.scalars(
            select(OperationCatalogEntry).where(
                or_(
                    OperationCatalogEntry.is_active.is_(True),
                    OperationCatalogEntry.id.in_(permitted_inactive_entry_ids),
                )
            )
        ).all()
        entries_by_id = {entry.id: entry for entry in entries}
        entries_by_name = {
            self._normalize_search(entry.name): entry for entry in entries
        }
        resolved_entries: dict[int, OperationCatalogEntry] = {}

        def walk(nodes: Sequence[OperationCreate]) -> None:
            for operation in nodes:
                if operation.children:
                    walk(operation.children)
                    continue

                entry = self._resolve_operation_catalog_entry(
                    operation,
                    entries_by_id,
                    entries_by_name,
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

    def _validate_created_operation_stages(
        self,
        operations: Sequence[OperationCreate],
        resolved_entries: dict[int, OperationCatalogEntry],
        stage_count: int,
    ) -> None:
        def walk(nodes: Sequence[OperationCreate]) -> None:
            for operation in nodes:
                if operation.children:
                    walk(operation.children)
                    continue

                self._validate_stage_range(
                    stage_start=operation.stage_start,
                    stage_end=operation.stage_end,
                    stage_count=stage_count,
                    operation_kind=resolved_entries[id(operation)].operation_kind,
                )

        walk(operations)

    def _validate_stage_range(
        self,
        *,
        stage_start: int,
        stage_end: int,
        stage_count: int,
        operation_kind: str | None,
    ) -> None:
        if stage_start > stage_end or stage_end > stage_count:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Диапазон операции должен находиться внутри этапов изделия.",
            )
        if (
            stage_start != stage_end
            and operation_kind != OperationCatalogEntryKind.ADJACENT.value
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Несмежная операция может находиться только на одном этапе.",
            )

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
    ) -> dict[int, OperationCostUpdate]:
        costs: dict[int, OperationCostUpdate] = {}

        def walk(nodes: Sequence[OperationCostUpdate]) -> None:
            for operation in nodes:
                if operation.id in costs:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail=(
                            "Operation prices must reference each operation only once."
                        ),
                    )

                costs[operation.id] = operation
                walk(operation.children)

        walk(operations)
        return costs

    def _serialize_operation(self, operation: Operation) -> OperationRead:
        ordered_children = sorted(operation.children, key=lambda item: item.sort_order)
        time_estimate = operation.time_estimate if not ordered_children else None
        return OperationRead(
            id=operation.id,
            operation_catalog_entry_id=operation.operation_catalog_entry_id,
            name=self._get_operation_name(operation),
            operation_kind=(
                operation.catalog_entry.operation_kind
                if operation.catalog_entry is not None
                else None
            ),
            coefficient_units=operation.coefficient_units,
            price_cents=None if ordered_children else operation.price_cents,
            standard_time_seconds=(
                None if ordered_children else operation.standard_time_seconds
            ),
            statistical_time_seconds=(
                time_estimate.seconds_per_item if time_estimate is not None else None
            ),
            statistical_completed_orders_count=(
                time_estimate.completed_orders_count if time_estimate is not None else 0
            ),
            statistical_items_count=(
                time_estimate.items_count if time_estimate is not None else 0
            ),
            statistical_time_calculated_at=(
                time_estimate.calculated_at if time_estimate is not None else None
            ),
            stage_start=operation.stage_start,
            stage_end=operation.stage_end,
            children=[self._serialize_operation(child) for child in ordered_children],
        )

    def _walk_operations(
        self,
        operations: Sequence[Operation],
    ) -> list[Operation]:
        result: list[Operation] = []
        for operation in operations:
            result.append(operation)
            result.extend(self._walk_operations(operation.children))
        return result

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
            stage_count=row.stage_count,
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
            return str(operation.catalog_entry.name)
        return operation.name
