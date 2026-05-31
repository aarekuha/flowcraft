from collections.abc import Callable, Generator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db_session
from app.services.auth_service import AuthenticatedSession


def get_session() -> Generator[Session, None, None]:
    yield from get_db_session()


def get_authenticated_session(request: Request) -> AuthenticatedSession:
    auth_session = getattr(request.state, "auth_session", None)
    if auth_session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется аутентификация.",
        )
    return auth_session


def require_any_role(*roles: str) -> Callable[..., AuthenticatedSession]:
    def dependency(
        auth_session: AuthenticatedSession = Depends(get_authenticated_session),
    ) -> AuthenticatedSession:
        if not any(role in auth_session.user_roles for role in roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав.",
            )
        return auth_session

    return dependency
