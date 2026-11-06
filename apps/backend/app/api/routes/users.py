from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_authenticated_session,
    get_session,
    require_any_role,
)
from app.schemas.user import UserCreate, UserRead, UserStatusUpdate, UserUpdate
from app.schemas.user_skill import UserSkillCreate, UserSkillsCopy, UserSkillsRead
from app.services.auth_service import AuthenticatedSession
from app.services.user_service import UserService
from app.services.user_skill_service import UserSkillService

router = APIRouter()


@router.get("", response_model=list[UserRead], summary="List active users")
def list_users(session: Session = Depends(get_session)) -> list[UserRead]:
    return UserService(session).list_users()


@router.get("/deleted", response_model=list[UserRead], summary="List deleted users")
def list_deleted_users(session: Session = Depends(get_session)) -> list[UserRead]:
    return UserService(session).list_deleted_users()


@router.get("/{user_id}", response_model=UserRead, summary="Get user")
def get_user(user_id: int, session: Session = Depends(get_session)) -> UserRead:
    return UserService(session).get_user(user_id)


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED, summary="Create user")
def create_user(payload: UserCreate, session: Session = Depends(get_session)) -> UserRead:
    return UserService(session).create_user(payload)


@router.put("/{user_id}", response_model=UserRead, summary="Update user")
def update_user(
    user_id: int,
    payload: UserUpdate,
    session: Session = Depends(get_session),
) -> UserRead:
    return UserService(session).update_user(user_id, payload)


@router.patch("/{user_id}/status", response_model=UserRead, summary="Update user status")
def update_user_status(
    user_id: int,
    payload: UserStatusUpdate,
    session: Session = Depends(get_session),
) -> UserRead:
    return UserService(session).update_user_status(user_id, payload)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Soft delete user")
def delete_user(user_id: int, session: Session = Depends(get_session)) -> Response:
    UserService(session).delete_user(user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{user_id}/reset-password", response_model=UserRead, summary="Reset user password")
def reset_user_password(user_id: int, session: Session = Depends(get_session)) -> UserRead:
    return UserService(session).reset_user_password(user_id)


@router.get(
    "/{user_id}/skills",
    response_model=UserSkillsRead,
    summary="List user operation skills",
)
def get_user_skills(
    user_id: int,
    _: object = Depends(require_any_role("admin")),
    session: Session = Depends(get_session),
) -> UserSkillsRead:
    return UserSkillService(session).get_user_skills(user_id)


@router.post(
    "/{user_id}/skills",
    response_model=UserSkillsRead,
    summary="Add user operation skill",
)
def add_user_skill(
    user_id: int,
    payload: UserSkillCreate,
    auth_session: AuthenticatedSession = Depends(get_authenticated_session),
    _: object = Depends(require_any_role("admin")),
    session: Session = Depends(get_session),
) -> UserSkillsRead:
    return UserSkillService(session).add_skill(
        user_id=user_id,
        operation_catalog_entry_id=payload.operation_catalog_entry_id,
        admin_user_id=auth_session.user_id,
    )


@router.delete(
    "/{user_id}/skills/{operation_catalog_entry_id}",
    response_model=UserSkillsRead,
    summary="Remove user operation skill",
)
def remove_user_skill(
    user_id: int,
    operation_catalog_entry_id: int,
    _: object = Depends(require_any_role("admin")),
    session: Session = Depends(get_session),
) -> UserSkillsRead:
    return UserSkillService(session).remove_skill(
        user_id=user_id,
        operation_catalog_entry_id=operation_catalog_entry_id,
    )


@router.post(
    "/{user_id}/skills/copy",
    response_model=UserSkillsRead,
    summary="Replace user operation skills from another user",
)
def copy_user_skills(
    user_id: int,
    payload: UserSkillsCopy,
    auth_session: AuthenticatedSession = Depends(get_authenticated_session),
    _: object = Depends(require_any_role("admin")),
    session: Session = Depends(get_session),
) -> UserSkillsRead:
    return UserSkillService(session).copy_skills(
        target_user_id=user_id,
        source_user_id=payload.source_user_id,
        admin_user_id=auth_session.user_id,
    )
