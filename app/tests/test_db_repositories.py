import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.base import Base
from app.db.repositories.user_repository import UserRepository
from app.db.repositories.symptom_repository import SymptomRepository

@pytest.fixture
def in_memory_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    sess = Session()
    yield sess
    sess.close()

def test_user_and_symptom_crud(in_memory_db):
    sess = in_memory_db
    ur = UserRepository(sess)
    sr = SymptomRepository(sess)

    user = ur.create(name="Tester", email="tester@example")
    assert user.id is not None
    assert user.name == "Tester"

    sym = sr.create(user_id=user.id, description="tosse")
    assert sym.id is not None
    assert sym.user_id == user.id

    last = sr.get_last_for_user(user.id)
    assert last.id == sym.id

    listed = sr.list_by_user(user.id)
    assert len(listed) == 1
