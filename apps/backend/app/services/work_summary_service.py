from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.completed_work import WorkSummary, WorkSummaryRow
from app.services.completed_work_service import CompletedWorkService
from app.services.xlsx_writer import CellValue, XlsxFormula, XlsxTotal, build_xlsx


class WorkSummaryService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def calculate(self, year: int, month: int) -> WorkSummary:
        users = self.session.scalars(
            select(User)
            .where(User.is_active.is_(True), User.deleted_at.is_(None))
            .order_by(User.name, User.id)
        ).all()
        service = CompletedWorkService(self.session)
        items = []
        for user in users:
            report = service.calculate(user.id, year, month)
            items.append(
                WorkSummaryRow(
                    incomplete=any(item.amount_cents is None for item in report.items),
                    user_id=user.id,
                    user_name=user.name,
                    sick_days=report.sick_days,
                    vacation_days=report.vacation_days,
                    piecework_cents=report.payable_piecework_cents,
                    bonuses_cents=report.bonuses_cents,
                )
            )
        return WorkSummary(year=year, month=month, items=items)

    def export(self, year: int, month: int) -> bytes:
        report = self.calculate(year, month)
        rows: list[list[CellValue]] = [
            ["ФИО", "Больничные", "Отпуск", "Сделка, ₽", "Премии, ₽"],
        ]
        for row in report.items:
            rows.append(
                [
                    row.user_name,
                    row.sick_days or None,
                    row.vacation_days or None,
                    (row.piecework_cents or 0) / 100,
                    row.bonuses_cents / 100,
                ]
            )
        last = len(rows)
        piecework = sum(row.piecework_cents or 0 for row in report.items) / 100
        bonuses = sum(row.bonuses_cents for row in report.items) / 100
        rows.append(
            [
                XlsxTotal("ИТОГО", gray=True),
                XlsxTotal(None, gray=True),
                XlsxTotal(None, gray=True),
                XlsxTotal(
                    XlsxFormula(
                        f"SUM(D2:D{last})" if report.items else "SUM(0)", piecework
                    ),
                    gray=True,
                ),
                XlsxTotal(
                    XlsxFormula(
                        f"SUM(E2:E{last})" if report.items else "SUM(0)", bonuses
                    ),
                    gray=True,
                ),
            ]
        )
        return build_xlsx(
            [(f"Расчёт {month:02}.{year}", rows)],
            auto_width=True,
            freeze_header=True,
        )
