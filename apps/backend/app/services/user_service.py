from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.phone import normalize_phone
from app.models.auth_session import AuthSession
from app.models.user import User
from app.schemas.user import UserCreate, UserRead, UserStatusUpdate, UserUpdate


class UserService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_users(self) -> list[UserRead]:
        stmt: Select[tuple[User]] = (
            select(User)
            .where(User.deleted_at.is_(None))
            .order_by(User.created_at.desc(), User.id.desc())
        )
        users = self.session.scalars(stmt).all()
        return [self._serialize_user(user) for user in users]

    def list_deleted_users(self) -> list[UserRead]:
        stmt: Select[tuple[User]] = (
            select(User)
            .where(User.deleted_at.is_not(None))
            .order_by(User.deleted_at.desc(), User.id.desc())
        )
        users = self.session.scalars(stmt).all()
        return [self._serialize_user(user) for user in users]

    def get_user(self, user_id: int) -> UserRead:
        user = self._get_user_or_404(user_id, include_deleted=True)
        return self._serialize_user(user)

    def create_user(self, payload: UserCreate) -> UserRead:
        self._ensure_phone_is_unique(payload.phone)
        timestamp = self._now_ts()
        user = User(
            name=payload.name,
            phone=payload.phone,
            password_hash=None,
            roles=[role.value for role in payload.roles],
            is_active=payload.is_active,
            created_at=timestamp,
            updated_at=timestamp,
            deleted_at=None,
            author_user_id=None,
        )
        self.session.add(user)
        self.session.flush()

        user.author_user_id = (
            self._resolve_author_user_id(payload.author_user_id) or user.id
        )

        self.session.commit()
        self.session.refresh(user)
        return self._serialize_user(user)

    def update_user(self, user_id: int, payload: UserUpdate) -> UserRead:
        user = self._get_user_or_404(user_id)
        self._ensure_phone_is_unique(payload.phone, exclude_user_id=user.id)
        self._ensure_admin_will_remain(
            user=user,
            next_roles=[role.value for role in payload.roles],
            next_is_active=payload.is_active,
            next_deleted_at=None,
        )
        user.name = payload.name
        user.phone = payload.phone
        user.roles = [role.value for role in payload.roles]
        user.is_active = payload.is_active
        user.author_user_id = (
            self._resolve_author_user_id(payload.author_user_id)
            if payload.author_user_id is not None
            else user.author_user_id
        )
        user.updated_at = self._now_ts()
        self.session.commit()
        self.session.refresh(user)
        return self._serialize_user(user)

    def update_user_status(self, user_id: int, payload: UserStatusUpdate) -> UserRead:
        user = self._get_user_or_404(user_id)
        self._ensure_admin_will_remain(
            user=user,
            next_roles=list(user.roles),
            next_is_active=payload.is_active,
            next_deleted_at=user.deleted_at,
        )
        user.is_active = payload.is_active
        user.updated_at = self._now_ts()
        self.session.commit()
        self.session.refresh(user)
        return self._serialize_user(user)

    def delete_user(self, user_id: int) -> None:
        user = self._get_user_or_404(user_id)
        timestamp = self._now_ts()
        self._ensure_admin_will_remain(
            user=user,
            next_roles=list(user.roles),
            next_is_active=user.is_active,
            next_deleted_at=timestamp,
        )
        user.deleted_at = timestamp
        user.updated_at = timestamp
        self._revoke_user_sessions(user.id, timestamp)
        self.session.commit()

    def reset_user_password(self, user_id: int) -> UserRead:
        user = self._get_user_or_404(user_id)
        timestamp = self._now_ts()
        user.password_hash = None
        user.updated_at = timestamp
        self._revoke_user_sessions(user.id, timestamp)
        self.session.commit()
        self.session.refresh(user)
        return self._serialize_user(user)

    def _get_user_or_404(self, user_id: int, *, include_deleted: bool = False) -> User:
        stmt: Select[tuple[User]] = select(User).where(User.id == user_id)
        if not include_deleted:
            stmt = stmt.where(User.deleted_at.is_(None))

        user = self.session.scalars(stmt).one_or_none()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found.",
            )
        return user

    def _serialize_user(self, user: User) -> UserRead:
        return UserRead(
            id=user.id,
            name=user.name,
            phone=user.phone,
            password_hash=user.password_hash,
            author=user.author_user.name if user.author_user is not None else None,
            author_user_id=user.author_user_id,
            roles=user.roles,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at,
            deleted_at=user.deleted_at,
        )

    def _now_ts(self) -> int:
        return int(datetime.now(UTC).timestamp() * 1000)

    def _resolve_author_user_id(self, author_user_id: int | None) -> int | None:
        if author_user_id is None:
            return None

        author_user = self.session.get(User, author_user_id)
        if author_user is None or author_user.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Author user not found.",
            )
        return author_user.id

    def _ensure_phone_is_unique(self, phone: str, *, exclude_user_id: int | None = None) -> None:
        normalized_phone = normalize_phone(phone)
        stmt: Select[tuple[User]] = select(User).where(User.deleted_at.is_(None))
        if exclude_user_id is not None:
            stmt = stmt.where(User.id != exclude_user_id)

        for user in self.session.scalars(stmt):
            try:
                if normalize_phone(user.phone) == normalized_phone:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail="Пользователь с таким номером телефона уже существует.",
                    )
            except ValueError:
                continue

    def _revoke_user_sessions(self, user_id: int, revoked_at: int) -> None:
        stmt: Select[tuple[AuthSession]] = select(AuthSession).where(
            AuthSession.user_id == user_id,
            AuthSession.revoked_at.is_(None),
        )
        for auth_session in self.session.scalars(stmt):
            auth_session.revoked_at = revoked_at

    def _ensure_admin_will_remain(
        self,
        *,
        user: User,
        next_roles: list[str],
        next_is_active: bool,
        next_deleted_at: int | None,
    ) -> None:
        if not self._is_admin_user(user.roles, user.is_active, user.deleted_at):
            return

        if self._is_admin_user(next_roles, next_is_active, next_deleted_at):
            return

        stmt: Select[tuple[User]] = select(User).where(User.id != user.id)
        for other_user in self.session.scalars(stmt):
            if self._is_admin_user(other_user.roles, other_user.is_active, other_user.deleted_at):
                return

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Нельзя убрать последнего активного администратора.",
        )

    def _is_admin_user(
        self,
        roles: list[str],
        is_active: bool,
        deleted_at: int | None,
    ) -> bool:
        return deleted_at is None and is_active and "admin" in roles
