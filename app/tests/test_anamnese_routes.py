import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.models.models import Anamnese, User
from app.models.schemas import AnamneseCreate
from app.routes.anamnese_routes import create_anamnese


class FakeQuery:
    def __init__(self, db):
        self.db = db

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        self.db.query_count += 1
        if self.db.query_count == 1:
            return None
        return Anamnese(id=99, user_id=1, info="existing")


class FakeSession:
    def __init__(self):
        self.query_count = 0
        self.rolled_back = False

    def query(self, *args, **kwargs):
        return FakeQuery(self)

    def add(self, item):
        self.item = item

    def commit(self):
        raise IntegrityError("insert", {}, Exception("unique violation"))

    def rollback(self):
        self.rolled_back = True


def test_create_anamnese_returns_conflict_when_unique_constraint_races():
    db = FakeSession()
    current_user = User(id=1, name="Paciente", email="paciente@example.com")

    with pytest.raises(HTTPException) as exc:
        create_anamnese(
            anamnese=AnamneseCreate(user_id=1, info="nova"),
            db=db,
            current_user=current_user,
        )

    assert exc.value.status_code == 409
    assert db.rolled_back is True
