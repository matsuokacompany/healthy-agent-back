from sqlalchemy.orm import Session
from fastapi import HTTPException
from passlib.context import CryptContext
from app.models.models import User
from app.models.schemas import UserCreate

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
            is_admin=False
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
