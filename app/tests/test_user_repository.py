import pytest
from app.db.base import SessionLocal, Base, engine
from app.db.repositories.user_repository import UserRepository

# Cria tabelas para testes
Base.metadata.create_all(bind=engine)

@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

def test_create_and_get_user(db):
    repo = UserRepository(db)
    user = repo.create("Igor", "igor@example.com")
    assert user.id is not None
    fetched = repo.get_user_by_email("igor@example.com")
    assert fetched.id == user.id
