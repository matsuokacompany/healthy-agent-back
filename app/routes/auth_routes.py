from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.core.auth import verify_password, create_access_token
from app.models.models import User

router = APIRouter(tags=["Auth"])


@router.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # OAuth2PasswordRequestForm envia username e password
    user = db.query(User).filter(User.email == form.username).first()

    if not user:
        raise HTTPException(401, "Invalid email or password")

    if not user.hashed_password:
        raise HTTPException(400, "User has no password configured")

    if not verify_password(form.password, user.hashed_password):
        raise HTTPException(401, "Invalid email or password")

    token = create_access_token(user.id, expires_delta=60)

    return {
        "access_token": token,
        "token_type": "bearer",
    }
