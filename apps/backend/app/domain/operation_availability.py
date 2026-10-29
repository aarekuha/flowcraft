from app.schemas.operation_catalog import OperationCatalogEntryKind
from app.schemas.order import WorkOrderProductionStage


def is_operation_available_for_stage(
    *,
    operation_kind: str,
    production_stage: str,
) -> bool:
    if production_stage == WorkOrderProductionStage.CUTTING.value:
        return operation_kind in {
            OperationCatalogEntryKind.CUTTING.value,
            OperationCatalogEntryKind.ADJACENT.value,
        }
    if production_stage == WorkOrderProductionStage.IN_WORK.value:
        return operation_kind in {
            OperationCatalogEntryKind.REGULAR.value,
            OperationCatalogEntryKind.ADJACENT.value,
        }
    return False
