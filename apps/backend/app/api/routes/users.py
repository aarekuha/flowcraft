from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.schemas.user import UserCreate, UserRead, UserStatusUpdate, UserUpdate
from app.services.user_service import UserService

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
