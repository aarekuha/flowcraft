from collections.abc import Iterator
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.planning import ProductionPlanningState
from app.models.user import User
from app.schemas.planning import WorkScheduleBatchDelete, WorkScheduleBatchUpdate
from app.services.planning_service import PlanningService


@pytest.fixture()
def schedule_session() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        for user_id in (1, 2, 3):
            session.add(
                User(
                    id=user_id,
                    name=f"Сотрудник {user_id}",
                    phone=str(user_id),
                    roles=["worker"],
                    is_active=True,
                    created_at=1,
                    updated_at=1,
                )
            )
        session.commit()
        yield session
    engine.dispose()


def test_multi_worker_update_and_delete_preserve_other_cells(
    schedule_session: Session,
) -> None:
    """
    Проверяем сохранение нескольких строк графика:
    - изменить разные наборы дат двух сотрудников одним запросом
    - сохранить соседние дни и строку третьего сотрудника
    - удалить выбранные записи и обновлять ревизию один раз за запрос
    """
    service = PlanningService(schedule_session)
    days = [date(2026, 11, day) for day in (2, 3, 4)]
    service.update_work_schedule(
        [
            WorkScheduleBatchUpdate(
                user_id=user, work_dates=days, available_seconds=28800
            )
            for user in (1, 2, 3)
        ],
        updated_by_user_id=1,
    )
    service.update_work_schedule(
        [
            WorkScheduleBatchUpdate(
                user_id=1,
                work_dates=days[:2],
                available_seconds=0,
                period_type="vacation",
            ),
            WorkScheduleBatchUpdate(
                user_id=2,
                work_dates=days[1:],
                available_seconds=0,
                period_type="vacation",
            ),
        ],
        updated_by_user_id=1,
    )
    schedule = {
        worker.user_id: worker.days
        for worker in service.get_work_schedule("2026-11").workers
    }
    assert [day.period_type for day in schedule[1]] == ["vacation", "vacation", "work"]
    assert [day.period_type for day in schedule[2]] == ["work", "vacation", "vacation"]
    assert [day.available_seconds for day in schedule[3]] == [28800] * 3
    service.delete_work_schedule(
        [
            WorkScheduleBatchDelete(user_id=1, work_dates=days[:2]),
            WorkScheduleBatchDelete(user_id=2, work_dates=days[1:]),
        ]
    )
    schedule = {
        worker.user_id: worker.days
        for worker in service.get_work_schedule("2026-11").workers
    }
    assert [day.work_date for day in schedule[1]] == days[2:]
    assert [day.work_date for day in schedule[2]] == days[:1]
    assert len(schedule[3]) == 3
    state = schedule_session.get(ProductionPlanningState, 1)
    assert state is not None and state.input_revision == 3


@pytest.mark.parametrize("action", ["update", "delete"])
def test_invalid_worker_rejects_entire_selection(
    schedule_session: Session,
    action: str,
) -> None:
    """
    Проверяем отсутствие частичного сохранения:
    - выбрать допустимого и отсутствующего сотрудника
    - отклонить изменение или удаление всего диапазона
    - сохранить исходные часы и ревизию расчёта
    """
    service = PlanningService(schedule_session)
    days = [date(2026, 11, 2)]
    service.update_work_schedule(
        WorkScheduleBatchUpdate(
            user_id=1,
            work_dates=days,
            available_seconds=28800,
        ),
        updated_by_user_id=1,
    )
    with pytest.raises(HTTPException) as error:
        if action == "update":
            service.update_work_schedule(
                [
                    WorkScheduleBatchUpdate(
                        user_id=user, work_dates=days, available_seconds=14400
                    )
                    for user in (1, 999)
                ],
                updated_by_user_id=1,
            )
        else:
            service.delete_work_schedule(
                [
                    WorkScheduleBatchDelete(user_id=user, work_dates=days)
                    for user in (1, 999)
                ]
            )
    assert error.value.status_code == 422
    schedule_session.commit()
    worker = service.get_work_schedule("2026-11").workers[0]
    assert worker.days[0].available_seconds == 28800
    state = schedule_session.get(ProductionPlanningState, 1)
    assert state is not None and state.input_revision == 1
