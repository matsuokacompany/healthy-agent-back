from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from passlib.context import CryptContext
from app.models.models import User
from app.models.schemas import UserCreate, UserUpdate
from app.core.access_control import UserRole, get_user_role

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class UserService:
    def __init__(self, db: Session):
        self.db = db

    def _hash_password(self, password: str) -> str:
        return pwd_context.hash(password[:72])

    def create_user(self, data: UserCreate) -> User:

        # Verifica email
        if self.db.query(User).filter(User.email == data.email).first():
            raise HTTPException(400, "Email already registered")

        # Verifica CPF
        if data.cpf and self.db.query(User).filter(User.cpf == data.cpf).first():
            raise HTTPException(400, "CPF already registered")

        # Verifica telegram_id
        if data.telegram_id and self.db.query(User).filter(User.telegram_id == data.telegram_id).first():
            raise HTTPException(400, "Telegram ID already registered")

        hashed_pw = None
        if data.password:
            hashed_pw = self._hash_password(data.password)

        role = data.role or (UserRole.PROFESSIONAL.value if data.is_admin else UserRole.PATIENT.value)

        new_user = User(
            name=data.name,
            email=data.email,
            phone=data.phone,
            telegram_id=data.telegram_id,
            city=data.city,
            state=data.state,
            gender=data.gender,
            birth_date=data.birth_date,
            cpf=data.cpf,
            hashed_password=hashed_pw,
            is_admin=role in {UserRole.PROFESSIONAL.value, UserRole.SUPER_ADMIN.value},
            role=role
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

        # Regra: só super admin pode mudar permissões administrativas/role
        current_role = get_user_role(current_user)
        if payload.is_admin is not None:
            if current_role != UserRole.SUPER_ADMIN:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only super admin can change admin permissions"
                )
            user.is_admin = payload.is_admin

        if payload.role is not None:
            if current_role != UserRole.SUPER_ADMIN:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only super admin can change user roles"
                )
            user.role = payload.role
            user.is_admin = payload.role in {UserRole.PROFESSIONAL.value, UserRole.SUPER_ADMIN.value}

        # Atualiza campos normais
        if payload.name is not None:
            user.name = payload.name
        if payload.email is not None:
            user.email = payload.email
        if payload.telegram_id is not None:
            user.telegram_id = payload.telegram_id
        if payload.phone is not None:
            user.phone = payload.phone
        if payload.city is not None:
            user.city = payload.city
        if payload.state is not None:
            user.state = payload.state
        if payload.gender is not None:
            user.gender = payload.gender
        if payload.birth_date is not None:
            user.birth_date = payload.birth_date
        if payload.cpf is not None:
            user.cpf = payload.cpf

        # Troca de senha
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