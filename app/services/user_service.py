from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from passlib.context import CryptContext

from app.models.models import User
from app.models.schemas import UserCreate, UserUpdate

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserService:
    def __init__(self, db: Session):
        self.db = db

    def _hash_password(self, password: str) -> str:
        return pwd_context.hash(password[:72])

    def create_user(self, data: UserCreate) -> User:

        # Email único
        if self.db.query(User).filter(User.email == data.email).first():
            raise HTTPException(400, "Email already registered")

        # CPF único
        if data.cpf and self.db.query(User).filter(User.cpf == data.cpf).first():
            raise HTTPException(400, "CPF already registered")

        # 🔴 TELEGRAM REMOVIDO (não validar mais canal externo aqui)
        # if data.telegram_id ...

        hashed_pw = None
        if data.password:
            hashed_pw = self._hash_password(data.password)

        new_user = User(
            name=data.name,
            email=data.email,
            phone=data.phone,
            telegram_id=None,  # mantém campo, mas não usado mais no fluxo
            city=data.city,
            state=data.state,
            gender=data.gender,
            birth_date=data.birth_date,
            cpf=data.cpf,
            hashed_password=hashed_pw,
            is_admin=False,
        )

        self.db.add(new_user)
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

    def update_user(self, user_id: int, payload: UserUpdate, current_user: User) -> User:
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Regra admin
        if payload.is_admin is not None:
            is_super_admin = (
                current_user.id == 1
                and current_user.email == "matsuokacompany@gmail.com"
            )
            if not is_super_admin:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only super admin can change admin permissions",
                )
            user.is_admin = payload.is_admin

        # Campos normais
        for field in [
            "name",
            "email",
            "phone",
            "city",
            "state",
            "gender",
            "birth_date",
            "cpf",
        ]:
            value = getattr(payload, field, None)
            if value is not None:
                setattr(user, field, value)

        # 🔴 TELEGRAM REMOVIDO DO UPDATE
        # if payload.telegram_id is not None:
        #     user.telegram_id = payload.telegram_id

        if payload.password is not None:
            user.hashed_password = self._hash_password(payload.password)

        self.db.commit()
        self.db.refresh(user)
        return user

    def delete_user(self, user_id: int):
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(404, "User not found")
        self.db.delete(user)
        self.db.commit()