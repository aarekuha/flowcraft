from datetime import UTC, datetime

from sqlalchemy import case, update
from sqlalchemy.orm import Session

from app.models.planning import ProductionPlanningState


class PlanningRevisionService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def request_recalculation(self) -> None:
        now = self._now_ts()
        result = self.session.execute(
            update(ProductionPlanningState)
            .where(ProductionPlanningState.id == 1)
            .values(
                input_revision=ProductionPlanningState.input_revision + 1,
                requested_revision=ProductionPlanningState.input_revision + 1,
                calculation_status=case(
                    (
                        ProductionPlanningState.calculation_status == "running",
                        "running",
                    ),
                    else_="pending",
                ),
                updated_at=now,
            )
            .returning(ProductionPlanningState.id)
            .execution_options(synchronize_session=False)
        )
        if result.scalar_one_or_none() is not None:
            return
        self.session.add(
            ProductionPlanningState(
                id=1,
                input_revision=1,
                requested_revision=1,
                active_run_id=None,
                calculation_status="pending",
                running_revision=None,
                worker_heartbeat_at=None,
                updated_at=now,
            )
        )

    def invalidate_without_recalculation(self) -> None:
        now = self._now_ts()
        result = self.session.execute(
            update(ProductionPlanningState)
            .where(ProductionPlanningState.id == 1)
            .values(
                input_revision=ProductionPlanningState.input_revision + 1,
                calculation_status=case(
                    (
                        ProductionPlanningState.calculation_status == "running",
                        "running",
                    ),
                    else_="idle",
                ),
                updated_at=now,
            )
            .returning(ProductionPlanningState.id)
            .execution_options(synchronize_session=False)
        )
        if result.scalar_one_or_none() is None:
            self.session.add(ProductionPlanningState(
                id=1, input_revision=1, requested_revision=0,
                active_run_id=None, calculation_status="idle", running_revision=None,
                worker_heartbeat_at=None, updated_at=now,
            ))

    def _now_ts(self) -> int:
        return int(datetime.now(UTC).timestamp() * 1000)
