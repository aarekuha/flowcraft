from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException, Response, status
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.phone import normalize_phone
from app.core.security import generate_session_token, hash_password, verify_password
from app.models.auth_session import AuthSession
from app.models.user import User
from app.schemas.auth import (
    AuthChangePassword,
    AuthLogin,
    AuthLoginResult,
    AuthSessionRead,
    AuthSetupPassword,
)

SESSION_COOKIE_NAME = "flowcraft_session"
SESSION_MAX_AGE_MS = 16 * 60 * 60 * 1000
SESSION_IDLE_MS = 2 * 60 * 60 * 1000


@dataclass(slots=True)
class AuthenticatedSession:
    session_id: int
    token: str
    user_id: int
    user_name: str
    user_roles: list[str]
    expires_at: int
    idle_expires_at: int


class AuthService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def login(self, payload: AuthLogin, response: Response) -> AuthLoginResult:
        user = self._get_user_by_phone(payload.phone)
        self._ensure_user_can_authenticate(user)

        if not user.password_hash:
            return AuthLoginResult(
                status="password_setup_required",
                user_name=user.name,
            )

        if not payload.password or not verify_password(
            payload.password,
            user.password_hash,
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный номер телефона или пароль.",
            )

        auth_session = self._create_session(user)
        self.session.commit()
        self._set_session_cookie(response, auth_session.token)
        return AuthLoginResult(
            status="authenticated",
            session=self._serialize_auth_session(auth_session),
            user_name=user.name,
        )

    def setup_password(
        self,
        payload: AuthSetupPassword,
        response: Response,
    ) -> AuthSessionRead:
        user = self._get_user_by_phone(payload.phone)
        self._ensure_user_can_authenticate(user)

        if user.password_hash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Пароль для этого пользователя уже задан.",
            )

        user.password_hash = hash_password(payload.new_password)
        user.updated_at = self._now_ts()
        auth_session = self._create_session(user)
        self.session.commit()
        self._set_session_cookie(response, auth_session.token)
        return self._serialize_auth_session(auth_session)

    def get_session(self, token: str | None) -> AuthenticatedSession:
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Требуется аутентификация.",
            )

        auth_session = self._get_auth_session_or_401(token)
        user = auth_session.user
        return AuthenticatedSession(
            session_id=auth_session.id,
            token=auth_session.token,
            user_id=auth_session.user_id,
            user_name=user.name,
            user_roles=list(user.roles),
            expires_at=auth_session.expires_at,
            idle_expires_at=auth_session.idle_expires_at,
        )

    def touch_session(self, session_id: int) -> None:
        auth_session = self.session.get(AuthSession, session_id)
        if auth_session is None or auth_session.revoked_at is not None:
            return

        now = self._now_ts()
        auth_session.last_seen_at = now
        auth_session.idle_expires_at = now + SESSION_IDLE_MS

        if auth_session.user is not None:
            auth_session.user_name = auth_session.user.name
            auth_session.user_roles = list(auth_session.user.roles)

        self.session.commit()

    def logout(self, token: str | None, response: Response) -> None:
        if token:
            stmt: Select[tuple[AuthSession]] = select(AuthSession).where(
                AuthSession.token == token,
                AuthSession.revoked_at.is_(None),
            )
            auth_session = self.session.scalars(stmt).one_or_none()
            if auth_session is not None:
                auth_session.revoked_at = self._now_ts()
                self.session.commit()

        self._clear_session_cookie(response)

    def change_password(
        self,
        auth_session: AuthenticatedSession,
        payload: AuthChangePassword,
        response: Response,
    ) -> AuthSessionRead:
        user = self._get_user_or_404(auth_session.user_id)

        if user.password_hash:
            if payload.current_password is None or not verify_password(
                payload.current_password,
                user.password_hash,
            ):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Текущий пароль указан неверно.",
                )

        user.password_hash = hash_password(payload.new_password)
        user.updated_at = self._now_ts()
        self._revoke_user_sessions(user.id)
        refreshed_session = self._create_session(user)
        self.session.commit()
        self._set_session_cookie(response, refreshed_session.token)
        return self._serialize_auth_session(refreshed_session)

    def clear_user_password(self, user_id: int) -> None:
        user = self._get_user_or_404(user_id)
        user.password_hash = None
        user.updated_at = self._now_ts()
        self._revoke_user_sessions(user.id)
        self.session.commit()

    def _create_session(self, user: User) -> AuthSession:
        now = self._now_ts()
        auth_session = AuthSession(
            token=generate_session_token(),
            user_id=user.id,
            user_name=user.name,
            user_roles=list(user.roles),
            created_at=now,
            last_seen_at=now,
            expires_at=now + SESSION_MAX_AGE_MS,
            idle_expires_at=now + SESSION_IDLE_MS,
            revoked_at=None,
        )
        self.session.add(auth_session)
        self.session.flush()
        return auth_session

    def _get_auth_session_or_401(self, token: str) -> AuthSession:
        stmt: Select[tuple[AuthSession]] = select(AuthSession).where(
            AuthSession.token == token,
            AuthSession.revoked_at.is_(None),
        )
        auth_session = self.session.scalars(stmt).one_or_none()
        now = self._now_ts()

        if (
            auth_session is None
            or auth_session.expires_at <= now
            or auth_session.idle_expires_at <= now
            or auth_session.user.deleted_at is not None
            or not auth_session.user.is_active
        ):
            if auth_session is not None and auth_session.revoked_at is None:
                auth_session.revoked_at = now
                self.session.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Сессия истекла. Войдите снова.",
            )

        return auth_session

    def _get_user_by_phone(self, phone: str) -> User:
        normalized_phone = normalize_phone(phone)
        stmt: Select[tuple[User]] = select(User).where(User.deleted_at.is_(None))

        for user in self.session.scalars(stmt):
            try:
                if normalize_phone(user.phone) == normalized_phone:
                    return user
            except ValueError:
                continue

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный номер телефона или пароль.",
        )

    def _get_user_or_404(self, user_id: int) -> User:
        user = self.session.get(User, user_id)
        if user is None or user.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found.",
            )
        return user

    def _ensure_user_can_authenticate(self, user: User) -> None:
        if user.deleted_at is not None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Пользователь не может пройти аутентификацию.",
            )

    def _revoke_user_sessions(self, user_id: int) -> None:
        now = self._now_ts()
        stmt: Select[tuple[AuthSession]] = select(AuthSession).where(
            AuthSession.user_id == user_id,
            AuthSession.revoked_at.is_(None),
        )
        for auth_session in self.session.scalars(stmt):
            auth_session.revoked_at = now

    def _serialize_auth_session(self, auth_session: AuthSession) -> AuthSessionRead:
        return AuthSessionRead(
            user_id=auth_session.user_id,
            user_name=auth_session.user_name,
            user_roles=auth_session.user_roles,
            expires_at=auth_session.expires_at,
            idle_expires_at=auth_session.idle_expires_at,
        )

    def _set_session_cookie(self, response: Response, token: str) -> None:
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=token,
            httponly=True,
            samesite="lax",
            secure=False,
            path="/",
        )

    def _clear_session_cookie(self, response: Response) -> None:
        response.delete_cookie(
            key=SESSION_COOKIE_NAME,
            httponly=True,
            samesite="lax",
            secure=False,
            path="/",
        )

    def _now_ts(self) -> int:
        return int(datetime.now(UTC).timestamp() * 1000)
