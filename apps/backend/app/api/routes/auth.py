from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_authenticated_session, get_session
from app.schemas.auth import (
    AuthChangePassword,
    AuthLogin,
    AuthLoginResult,
    AuthSessionRead,
    AuthSetupPassword,
)
from app.services.auth_service import AuthService, AuthenticatedSession, SESSION_COOKIE_NAME

router = APIRouter()


@router.post("/login", response_model=AuthLoginResult, summary="Login")
def login(
    payload: AuthLogin,
    response: Response,
    session: Session = Depends(get_session),
) -> AuthLoginResult:
    return AuthService(session).login(payload, response)


@router.post("/setup-password", response_model=AuthSessionRead, summary="Set initial password")
def setup_password(
    payload: AuthSetupPassword,
    response: Response,
    session: Session = Depends(get_session),
) -> AuthSessionRead:
    return AuthService(session).setup_password(payload, response)


@router.get("/me", response_model=AuthSessionRead, summary="Current session")
def get_current_session(
    auth_session: AuthenticatedSession = Depends(get_authenticated_session),
) -> AuthSessionRead:
    return AuthSessionRead(
        user_id=auth_session.user_id,
        user_name=auth_session.user_name,
        user_roles=auth_session.user_roles,
        expires_at=auth_session.expires_at,
        idle_expires_at=auth_session.idle_expires_at,
    )


@router.post("/change-password", response_model=AuthSessionRead, summary="Change password")
def change_password(
    payload: AuthChangePassword,
    response: Response,
    auth_session: AuthenticatedSession = Depends(get_authenticated_session),
    session: Session = Depends(get_session),
) -> AuthSessionRead:
    return AuthService(session).change_password(auth_session, payload, response)


@router.post("/logout", status_code=204, summary="Logout")
def logout(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> Response:
    AuthService(session).logout(request.cookies.get(SESSION_COOKIE_NAME), response)
    response.status_code = 204
    return response
