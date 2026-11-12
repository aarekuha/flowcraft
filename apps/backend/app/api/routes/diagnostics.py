# ruff: noqa: I001
from datetime import UTC, datetime
import zlib

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_authenticated_session,
    get_session,
    require_any_role,
)
from app.models.diagnostic_report import DiagnosticReport
from app.schemas.diagnostics import DiagnosticUpload
from app.services.auth_service import AuthenticatedSession

router = APIRouter()


async def parse_report(request: Request) -> DiagnosticUpload:
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 2 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Отчёт слишком большой.")
    try:
        encoding = request.headers.get("content-encoding", "identity")
        if encoding == "gzip":
            decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
            data = decoder.decompress(bytes(raw), 16 * 1024 * 1024 + 1)
            if len(data) > 16 * 1024 * 1024 or decoder.unconsumed_tail:
                raise HTTPException(status_code=413, detail="Отчёт слишком большой.")
            if not decoder.eof or decoder.unused_data:
                raise ValueError("Invalid gzip stream")
        elif encoding == "identity":
            data = bytes(raw)
        else:
            raise HTTPException(
                status_code=415, detail="Неподдерживаемый формат отчёта."
            )
        return DiagnosticUpload.model_validate_json(data)
    except (ValueError, zlib.error) as error:
        raise HTTPException(
            status_code=422, detail="Некорректный отчёт диагностики."
        ) from error


@router.post("/reports")
def upload_report(
    payload: DiagnosticUpload = Depends(parse_report),
    auth: AuthenticatedSession = Depends(get_authenticated_session),
    session: Session = Depends(get_session),
) -> dict[str, int]:
    if payload.owner_user_id != auth.user_id:
        raise HTTPException(
            status_code=403,
            detail="Пользователь изменился. Повторить отправку из своей учётной записи",
        )
    key = str(payload.report_key)
    existing = session.scalar(
        select(DiagnosticReport).where(
            DiagnosticReport.user_id == auth.user_id,
            DiagnosticReport.report_key == key,
        )
    )
    if existing is not None:
        return {"id": existing.id}
    now = int(datetime.now(UTC).timestamp() * 1000)
    report = DiagnosticReport(
        user_id=auth.user_id,
        report_key=key,
        created_at=now,
        payload=payload.model_dump(mode="json"),
    )
    session.add(report)
    session.execute(
        delete(DiagnosticReport).where(
            DiagnosticReport.created_at < now - 30 * 86400000
        )
    )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(
            select(DiagnosticReport).where(
                DiagnosticReport.user_id == auth.user_id,
                DiagnosticReport.report_key == key,
            )
        )
        if existing is None:
            raise
        return {"id": existing.id}
    return {"id": report.id}


@router.get("/reports")
def list_reports(
    _: object = Depends(require_any_role("admin")),
    session: Session = Depends(get_session),
) -> list[dict[str, int]]:
    reports = session.scalars(
        select(DiagnosticReport).order_by(DiagnosticReport.id.desc()).limit(100)
    ).all()
    return [
        {"id": item.id, "user_id": item.user_id, "created_at": item.created_at}
        for item in reports
    ]


@router.get("/reports/{report_id}")
def get_report(
    report_id: int,
    _: object = Depends(require_any_role("admin")),
    session: Session = Depends(get_session),
) -> dict:
    report = session.get(DiagnosticReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Отчёт не найден.")
    return {
        "id": report.id,
        "user_id": report.user_id,
        "created_at": report.created_at,
        "report": report.payload,
    }
