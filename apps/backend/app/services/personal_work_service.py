import hashlib
import hmac
import time

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.models.user import User
from app.schemas.completed_work import PersonalReportAccess, PersonalWorkReport
from app.services.auth_service import AuthenticatedSession
from app.services.completed_work_service import CompletedWorkService

ACCESS_SECONDS = 15 * 60


class PersonalWorkService:
    def __init__(self, session: Session, auth: AuthenticatedSession) -> None:
        self.session = session
        self.auth = auth

    def _user(self) -> User:
        user = self.session.get(User, self.auth.user_id)
        if user is None or user.deleted_at is not None or not user.is_active:
            raise HTTPException(403, "Просмотр расчёта недоступен")
        return user

    def _signature(self, user: User, expires: int) -> str:
        message = (
            f"personal-work:{self.auth.session_id}:{user.id}:"
            f"{expires}:{user.password_hash}"
        )
        return hmac.new(
            self.auth.token.encode(), message.encode(), hashlib.sha256
        ).hexdigest()

    def unlock(self, password: str) -> PersonalReportAccess:
        user = self._user()
        if not user.password_hash or not verify_password(
            password.strip(), user.password_hash
        ):
            raise HTTPException(403, "Неверный пароль текущего пользователя")
        expires = int(time.time()) + ACCESS_SECONDS
        return PersonalReportAccess(
            token=f"{expires}.{self._signature(user, expires)}",
            expires_at=expires * 1000,
        )

    def calculate(self, token: str, year: int, month: int) -> PersonalWorkReport:
        user = self._user()
        try:
            expires_text, signature = token.split(".", 1)
            expires = int(expires_text)
        except (ValueError, TypeError):
            raise HTTPException(403, "Для просмотра расчёта требуется пароль") from None
        if (
            expires <= int(time.time())
            or len(signature) != 64
            or any(char not in "0123456789abcdef" for char in signature)
            or not hmac.compare_digest(signature, self._signature(user, expires))
        ):
            raise HTTPException(
                403, "Повторно подтвердить пароль для просмотра расчёта"
            )
        report = CompletedWorkService(self.session).calculate(user.id, year, month)
        return PersonalWorkReport.model_validate(report.model_dump())
