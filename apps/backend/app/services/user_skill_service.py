from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.operation_catalog import OperationCatalogEntry
from app.models.user import User
from app.models.user_operation_skill import UserOperationSkill
from app.schemas.user_skill import UserSkillRead, UserSkillsRead
from app.services.planning_revision_service import PlanningRevisionService


class UserSkillService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_user_skills(self, user_id: int) -> UserSkillsRead:
        user = self._get_user_or_404(user_id)
        return self._serialize_user_skills(user)

    def add_skill(
        self,
        *,
        user_id: int,
        operation_catalog_entry_id: int,
        admin_user_id: int,
    ) -> UserSkillsRead:
        user = self._get_user_or_404(user_id)
        entry = self.session.get(
            OperationCatalogEntry,
            operation_catalog_entry_id,
        )
        if entry is None or not entry.is_active:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Добавить можно только активную операцию справочника.",
            )
        existing_skill = self.session.scalar(
            select(UserOperationSkill).where(
                UserOperationSkill.user_id == user.id,
                UserOperationSkill.operation_catalog_entry_id == entry.id,
            )
        )
        if existing_skill is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Навык уже добавлен пользователю.",
            )

        self.session.add(
            UserOperationSkill(
                user_id=user.id,
                operation_catalog_entry_id=entry.id,
                created_at=self._now_ts(),
                created_by_user_id=admin_user_id,
            )
        )
        PlanningRevisionService(self.session).request_recalculation()
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            existing_skill = self.session.scalar(
                select(UserOperationSkill).where(
                    UserOperationSkill.user_id == user.id,
                    UserOperationSkill.operation_catalog_entry_id == entry.id,
                )
            )
            if existing_skill is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Навык уже добавлен пользователю.",
                ) from None
            raise
        return self.get_user_skills(user.id)

    def remove_skill(
        self,
        *,
        user_id: int,
        operation_catalog_entry_id: int,
    ) -> UserSkillsRead:
        user = self._get_user_or_404(user_id)
        skill = self.session.scalar(
            select(UserOperationSkill).where(
                UserOperationSkill.user_id == user.id,
                UserOperationSkill.operation_catalog_entry_id
                == operation_catalog_entry_id,
            )
        )
        if skill is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Навык пользователя не найден.",
            )
        self.session.delete(skill)
        PlanningRevisionService(self.session).request_recalculation()
        self.session.commit()
        return self.get_user_skills(user.id)

    def copy_skills(
        self,
        *,
        target_user_id: int,
        source_user_id: int,
        admin_user_id: int,
    ) -> UserSkillsRead:
        if target_user_id == source_user_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Необходимо выбрать другого пользователя.",
            )
        target_user = self._get_user_or_404(target_user_id)
        source_user = self._get_user_or_404(source_user_id)
        source_operation_ids = sorted(
            skill.operation_catalog_entry_id
            for skill in source_user.operation_skills
        )
        now = self._now_ts()

        self.session.execute(
            delete(UserOperationSkill).where(
                UserOperationSkill.user_id == target_user.id
            )
        )
        self.session.add_all(
            [
                UserOperationSkill(
                    user_id=target_user.id,
                    operation_catalog_entry_id=operation_id,
                    created_at=now,
                    created_by_user_id=admin_user_id,
                )
                for operation_id in source_operation_ids
            ]
        )
        PlanningRevisionService(self.session).request_recalculation()
        self.session.commit()
        return self.get_user_skills(target_user.id)

    def _get_user_or_404(self, user_id: int) -> User:
        user = self.session.scalar(
            select(User)
            .options(
                selectinload(User.operation_skills).selectinload(
                    UserOperationSkill.operation_catalog_entry
                )
            )
            .where(
                User.id == user_id,
                User.deleted_at.is_(None),
            )
        )
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found.",
            )
        return user

    def _serialize_user_skills(self, user: User) -> UserSkillsRead:
        active_skills = [
            skill
            for skill in user.operation_skills
            if skill.operation_catalog_entry.is_active
        ]
        active_skills.sort(
            key=lambda skill: (
                skill.operation_catalog_entry.name.casefold(),
                skill.operation_catalog_entry_id,
            )
        )
        return UserSkillsRead(
            user_id=user.id,
            user_name=user.name,
            skills=[
                UserSkillRead(
                    operation_catalog_entry_id=skill.operation_catalog_entry_id,
                    operation_name=skill.operation_catalog_entry.name,
                    operation_kind=skill.operation_catalog_entry.operation_kind,
                    created_at=skill.created_at,
                )
                for skill in active_skills
            ],
            total_count=len(user.operation_skills),
            hidden_inactive_count=len(user.operation_skills) - len(active_skills),
        )

    def _now_ts(self) -> int:
        return int(datetime.now(UTC).timestamp() * 1000)
