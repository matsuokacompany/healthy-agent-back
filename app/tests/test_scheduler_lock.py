from app.bot.scheduler import _release_scheduler_lock, _try_acquire_scheduler_lock


class FakeDialect:
    def __init__(self, name):
        self.name = name


class FakeBind:
    def __init__(self, dialect_name):
        self.dialect = FakeDialect(dialect_name)


class FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


class FakeDb:
    def __init__(self, dialect_name="postgresql", scalar=True):
        self.bind = FakeBind(dialect_name)
        self.scalar = scalar
        self.calls = []

    def get_bind(self):
        return self.bind

    def execute(self, statement, params):
        self.calls.append((str(statement), params))
        return FakeResult(self.scalar)


def test_try_acquire_scheduler_lock_uses_postgresql_advisory_lock():
    db = FakeDb(scalar=True)

    assert _try_acquire_scheduler_lock(db, lock_id=123) is True
    assert "pg_try_advisory_lock" in db.calls[0][0]
    assert db.calls[0][1] == {"lock_id": 123}


def test_try_acquire_scheduler_lock_returns_false_when_lock_is_busy():
    db = FakeDb(scalar=False)

    assert _try_acquire_scheduler_lock(db, lock_id=123) is False


def test_release_scheduler_lock_uses_postgresql_advisory_unlock():
    db = FakeDb()

    _release_scheduler_lock(db, lock_id=123)

    assert "pg_advisory_unlock" in db.calls[0][0]
    assert db.calls[0][1] == {"lock_id": 123}


def test_scheduler_lock_is_noop_for_non_postgresql_database():
    db = FakeDb(dialect_name="sqlite")

    assert _try_acquire_scheduler_lock(db, lock_id=123) is True
    _release_scheduler_lock(db, lock_id=123)

    assert db.calls == []
