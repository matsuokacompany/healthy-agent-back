import logging
import traceback
import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import assign_role
from app.core.permissions import is_super_admin
from app.models.models import RoleNameEnum, User, UserRole
from app.models.schemas import UserCreate, UserRoleUpdate, UserUpdate

logger = logging.getLogger(__name__)


class UserService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _normalize_phone(phone: str | None) -> str | None:
        if not phone:
            return None
        return "".join(ch for ch in phone if ch.isdigit())

    def create_user(self, data: UserCreate, current_user: User) -> User:
        if self.db.query(User).filter(User.email == data.email).first():
            raise HTTPException(400, "Email already registered")
        if data.cpf and self.db.query(User).filter(User.cpf == data.cpf).first():
            raise HTTPException(400, "CPF already registered")

        requested_role_values = {role.value for role in data.roles}
        privileged_roles = {RoleNameEnum.ADMIN.value, RoleNameEnum.SUPER_ADMIN.value}
        if requested_role_values & privileged_roles and not is_super_admin(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only super admins can assign admin or super_admin roles",
            )

        supabase_user_id = uuid.UUID(data.supabase_user_id) if data.supabase_user_id else None
        if supabase_user_id and self.db.query(User).filter(User.supabase_user_id == supabase_user_id).first():
            raise HTTPException(400, "Supabase user already linked")

        new_user = User(
            name=data.name,
            email=data.email,
            supabase_user_id=supabase_user_id,
            phone=self._normalize_phone(data.phone),
            city=data.city,
            state=data.state,
            gender=data.gender,
            birth_date=data.birth_date,
            cpf=data.cpf,
            is_admin=any(role.value in {RoleNameEnum.ADMIN.value, RoleNameEnum.SUPER_ADMIN.value} for role in data.roles),
        )
        self.db.add(new_user)
        self.db.flush()
        for role in data.roles or [RoleNameEnum.PATIENT]:
            assign_role(self.db, new_user, RoleNameEnum(role.value))
        self.db.commit()
        self.db.refresh(new_user)
        return new_user

    def get_user(self, user_id: int) -> User:
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(404, "User not found")
        return user

    def list_users(self) -> list[User]:
        return self.db.query(User).all()

    def update_user(self, user_id: int, payload: UserUpdate) -> User:
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        for field in ["name", "email", "phone", "city", "state", "gender", "birth_date", "cpf"]:
            value = getattr(payload, field, None)
            if value is not None:
                if field == "phone":
                    value = self._normalize_phone(value)
                current_value = getattr(user, field)
                if value != current_value:
                    logger.warning(
                        "Updating public.users user_id=%s previous_name=%r new_name=%r origin=%s field=%s stack=%s",
                        user.id,
                        user.name,
                        value if field == "name" else user.name,
                        "UserService.update_user",
                        field,
                        "".join(traceback.format_stack(limit=8)),
                    )
                    setattr(user, field, value)

        self.db.commit()
        self.db.refresh(user)
        return user

    def update_roles(self, user_id: int, payload: UserRoleUpdate, current_user: User) -> User:
        if not is_super_admin(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only super admins can change user roles",
            )
        user = self.get_user(user_id)
        logger.warning(
            "Updating public.users user_id=%s previous_name=%r new_name=%r origin=%s field=roles stack=%s",
            user.id,
            user.name,
            user.name,
            "UserService.update_roles",
            "".join(traceback.format_stack(limit=8)),
        )
        self.db.query(UserRole).filter(UserRole.user_id == user.id).delete()
        self.db.flush()
        for role in payload.roles:
            assign_role(self.db, user, RoleNameEnum(role.value))
        new_is_admin = any(role.value in {RoleNameEnum.ADMIN.value, RoleNameEnum.SUPER_ADMIN.value} for role in payload.roles)
        if user.is_admin != new_is_admin:
            logger.warning(
                "Updating public.users user_id=%s previous_name=%r new_name=%r origin=%s field=is_admin stack=%s",
                user.id,
                user.name,
                user.name,
                "UserService.update_roles",
                "".join(traceback.format_stack(limit=8)),
            )
        user.is_admin = new_is_admin
        self.db.commit()
        self.db.refresh(user)
        return user

    def delete_user(self, user_id: int):
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(404, "User not found")
        self.db.delete(user)
        self.db.commit()
