# ruff: noqa: I001

from datetime import date, datetime
from decimal import ROUND_CEILING, Decimal
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.bonus import Bonus, UserBonus, MonthlyBonusExclusion
from app.models.operation import Operation
from app.models.operation_catalog import OperationCatalogEntry
from app.models.planning import UserWorkScheduleDay
from app.models.product import Product
from app.models.user import User
from app.models.work_order import WorkOrder
from app.schemas.completed_work import (
    BonusRead,
    CompletedWorkReport,
    CompletedWorkRow,
    CompletedWorkBonus,
)
from app.services.effective_order_time import build_effective_operation_time_subquery
from app.services.xlsx_writer import SheetRows, XlsxFormula, XlsxTotal, build_xlsx

MOSCOW = ZoneInfo("Europe/Moscow")


class CompletedWorkService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_user(self, user_id: int) -> User:
        user = self.session.get(User, user_id)
        if user is None or user.deleted_at is not None:
            raise HTTPException(404, "Сотрудник не найден")
        return user

    def bonuses(self, user_id: int) -> list[BonusRead]:
        self.get_user(user_id)
        return [
            BonusRead.model_validate(bonus)
            for bonus in self.session.scalars(
                select(Bonus)
                .join(UserBonus, UserBonus.bonus_id == Bonus.id)
                .where(UserBonus.user_id == user_id)
                .order_by(Bonus.name, Bonus.id)
            )
        ]

    def set_bonus_selection(
        self, user_id: int, year: int, month: int, bonus_id: int, *, selected: bool
    ) -> CompletedWorkReport:
        self.get_user(user_id)
        if self.session.get(UserBonus, (user_id, bonus_id)) is None:
            raise HTTPException(404, "Премия не назначена сотруднику")
        exclusion = self.session.get(
            MonthlyBonusExclusion, (user_id, year, month, bonus_id)
        )
        if selected and exclusion is not None:
            self.session.delete(exclusion)
        elif not selected and exclusion is None:
            self.session.add(
                MonthlyBonusExclusion(
                    user_id=user_id,
                    year=year,
                    month=month,
                    bonus_id=bonus_id,
                )
            )
        self.session.commit()
        return self.calculate(user_id, year, month)

    def calculate(self, user_id: int, year: int, month: int) -> CompletedWorkReport:
        user = self.get_user(user_id)
        start = date(year, month, 1)
        end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        start_ms = int(
            datetime.combine(start, datetime.min.time(), MOSCOW).timestamp() * 1000
        )
        end_ms = int(
            datetime.combine(end, datetime.min.time(), MOSCOW).timestamp() * 1000
        )
        effective = build_effective_operation_time_subquery()
        times = self.session.execute(
            select(
                effective.c.order_id,
                effective.c.operation_id,
                effective.c.user_id,
                func.sum(effective.c.elapsed_ms).label("elapsed_ms"),
            )
            .join(WorkOrder, WorkOrder.id == effective.c.order_id)
            .where(
                WorkOrder.deleted_at.is_(None),
                WorkOrder.completed_at >= start_ms,
                WorkOrder.completed_at < end_ms,
                effective.c.elapsed_ms > 0,
            )
            .group_by(
                effective.c.order_id, effective.c.operation_id, effective.c.user_id
            )
        ).all()
        totals: dict[tuple[int, int | None], int] = {}
        own: dict[tuple[int, int | None], int] = {}
        for row in times:
            key = (row.order_id, row.operation_id)
            totals[key] = totals.get(key, 0) + row.elapsed_ms
            if row.user_id == user_id:
                own[key] = row.elapsed_ms
        orders = {
            row.id: row
            for row in self.session.scalars(
                select(WorkOrder).where(WorkOrder.id.in_({key[0] for key in own}))
            ).unique()
        }
        operation_ids = {key[1] for key in own if key[1] is not None}
        operations = {
            row.id: row
            for row in self.session.scalars(
                select(Operation).where(Operation.id.in_(operation_ids))
            ).unique()
        }
        products = {
            row.id: row
            for row in self.session.scalars(
                select(Product).where(
                    Product.id.in_({order.product_id for order in orders.values()})
                )
            ).unique()
        }
        names = {
            entry_id: name
            for entry_id, name in self.session.execute(
                select(OperationCatalogEntry.id, OperationCatalogEntry.name)
            )
        }
        items: list[CompletedWorkRow] = []
        max_quantities: dict[int, Decimal] = {}
        for key, elapsed in own.items():
            order_id, operation_id = key
            order = orders[order_id]
            product = products[order.product_id]
            operation = (
                operations.get(operation_id) if operation_id is not None else None
            )
            quantity = (
                Decimal(max(order.quantity - order.defect_quantity, 0))
                * elapsed
                / totals[key]
            ).quantize(Decimal("0.01"), rounding=ROUND_CEILING)
            price = operation.price_cents if operation else None
            amount = (
                int((quantity * price).to_integral_value(rounding=ROUND_CEILING))
                if price is not None
                else None
            )
            max_quantities[order_id] = max(
                max_quantities.get(order_id, Decimal(0)), quantity
            )
            items.append(
                CompletedWorkRow(
                    order_id=order_id,
                    order_number=order.order_number,
                    completed_at=order.completed_at or 0,
                    product_name=product.name,
                    product_version=product.version,
                    operation_id=operation_id,
                    operation_name=(
                        names.get(
                            operation.operation_catalog_entry_id or 0, operation.name
                        )
                        if operation
                        else "Операция удалена"
                    ),
                    quantity=quantity,
                    price_cents=price,
                    amount_cents=amount,
                )
            )
        items.sort(
            key=lambda row: (
                row.order_number,
                row.operation_name,
                row.operation_id or 0,
            )
        )
        days = list(
            self.session.scalars(
                select(UserWorkScheduleDay).where(
                    UserWorkScheduleDay.user_id == user_id,
                    UserWorkScheduleDay.work_date >= start,
                    UserWorkScheduleDay.work_date < end,
                )
            )
        )
        excluded_ids = set(
            self.session.scalars(
                select(MonthlyBonusExclusion.bonus_id).where(
                    MonthlyBonusExclusion.user_id == user_id,
                    MonthlyBonusExclusion.year == year,
                    MonthlyBonusExclusion.month == month,
                )
            )
        )
        bonuses = [
            CompletedWorkBonus(
                **bonus.model_dump(), selected=bonus.id not in excluded_ids
            )
            for bonus in self.bonuses(user_id)
        ]
        bonuses_cents = sum(bonus.amount_cents for bonus in bonuses if bonus.selected)
        piecework = (
            sum(row.amount_cents or 0 for row in items)
            if all(row.amount_cents is not None for row in items)
            else None
        )
        return CompletedWorkReport(
            user_id=user_id,
            user_name=user.name,
            year=year,
            month=month,
            work_days=sum(day.period_type == "work" for day in days),
            work_hours=Decimal(
                sum(day.available_seconds for day in days if day.period_type == "work")
            )
            / 3600,
            sick_days=sum(day.period_type == "sick_leave" for day in days),
            vacation_days=sum(day.period_type == "vacation" for day in days),
            absence_days=sum(day.period_type == "absence" for day in days),
            items=items,
            total_quantity=sum(max_quantities.values(), Decimal(0)),
            piecework_cents=piecework,
            bonuses=bonuses,
            bonuses_cents=bonuses_cents,
            payout_cents=piecework + bonuses_cents if piecework is not None else None,
        )

    def export(self, user_id: int, year: int, month: int) -> bytes:
        report = self.calculate(user_id, year, month)
        if report.piecework_cents is None:
            raise HTTPException(
                409, "Для выгрузки указать расценки всех операций расчёта"
            )
        rows: list[list] = [
            ["Расчёт выполненной работы"],
            ["ФИО", report.user_name],
            ["Период", f"{month:02}.{year}"],
            ["Рабочих дней по графику", report.work_days],
            ["Часов по графику", float(report.work_hours)],
            ["Больничных дней", report.sick_days],
            ["Дней отпуска", report.vacation_days],
            ["Дней прогулов", report.absence_days],
            [],
            [
                "Номер заказа",
                "Дата сдачи",
                "Изделие и версия",
                "Операция",
                "Количество изделий",
                "Расценка, ₽",
                "Начисление, ₽",
            ],
        ]
        for row in report.items:
            rows.append(
                [
                    row.order_number,
                    datetime.fromtimestamp(row.completed_at / 1000, MOSCOW).strftime(
                        "%d.%m.%Y"
                    ),
                    f"{row.product_name} · {row.product_version}",
                    row.operation_name,
                    float(row.quantity),
                    (row.price_cents or 0) / 100,
                    (row.amount_cents or 0) / 100,
                ]
            )
        rows.append(
            [
                XlsxTotal("Итого"),
                None,
                None,
                None,
                XlsxTotal(float(report.total_quantity)),
                None,
                XlsxTotal(report.piecework_cents / 100),
            ]
        )
        rows.append(
            [None, None, None, None, None, "Сделка", report.piecework_cents / 100]
        )
        piecework_cell = f"G{len(rows)}"
        rows.extend([[], ["Премии", "Сумма, ₽"]])
        rows.extend(
            [
                [bonus.name, bonus.amount_cents / 100]
                for bonus in report.bonuses
                if bonus.selected
            ]
        )
        rows.append(["Итого премий", report.bonuses_cents / 100])
        bonus_cell = f"B{len(rows)}"
        rows.append(
            [
                "Выплата",
                XlsxFormula(
                    f"{bonus_cell}+{piecework_cell}", (report.payout_cents or 0) / 100
                ),
            ]
        )
        sheet: SheetRows = rows
        return build_xlsx([("Выполненная работа", sheet)], auto_width=True)
