import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.auth import _sync_supabase_profile
from app.db.base_class import Base
from app.models.models import User


def build_session():
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal()


def create_user(db, *, email="old@example.com", name="Old Name", supabase_user_id=None):
    user = User(
        name=name,
        email=email,
        supabase_user_id=supabase_user_id or uuid.uuid4(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_sync_updates_email_from_supabase_without_changing_identity_link():
    db = build_session()
    supabase_user_id = uuid.uuid4()
    user = create_user(db, supabase_user_id=supabase_user_id)

    _sync_supabase_profile(
        db,
        user,
        {
            "sub": str(supabase_user_id),
            "email": "new@example.com",
            "user_metadata": {"name": "Old Name"},
        },
    )
    db.commit()
    db.refresh(user)

    assert user.supabase_user_id == supabase_user_id
    assert user.email == "new@example.com"


def test_sync_does_not_replace_name_when_supabase_metadata_is_missing():
    db = build_session()
    user = create_user(db, name="Igor", email="igor@email.com")

    _sync_supabase_profile(
        db,
        user,
        {
            "sub": str(user.supabase_user_id),
            "email": user.email,
            "user_metadata": {},
        },
    )
    db.commit()
    db.refresh(user)

    assert user.name == "Igor"


def test_sync_does_not_replace_name_with_email_from_supabase_metadata():
    db = build_session()
    user = create_user(db, name="Igor", email="igor@email.com")

    _sync_supabase_profile(
        db,
        user,
        {
            "sub": str(user.supabase_user_id),
            "email": user.email,
            "user_metadata": {"name": user.email},
        },
    )
    db.commit()
    db.refresh(user)

    assert user.name == "Igor"


def test_sync_updates_name_from_supabase_metadata():
    db = build_session()
    user = create_user(db, name="Old Name")

    _sync_supabase_profile(
        db,
        user,
        {
            "sub": str(user.supabase_user_id),
            "email": user.email,
            "user_metadata": {"name": "New Name"},
        },
    )
    db.commit()
    db.refresh(user)

    assert user.name == "New Name"


def test_sync_keeps_supabase_uuid_as_identity_source_when_email_changes():
    db = build_session()
    supabase_user_id = uuid.uuid4()
    user = create_user(db, email="first@example.com", supabase_user_id=supabase_user_id)

    _sync_supabase_profile(
        db,
        user,
        {
            "sub": str(supabase_user_id),
            "email": "second@example.com",
            "user_metadata": {"name": user.name},
        },
    )
    db.commit()

    found = db.query(User).filter(User.supabase_user_id == supabase_user_id).first()
    assert found.id == user.id
    assert found.email == "second@example.com"


def test_sync_blocks_email_conflict_with_another_local_user():
    db = build_session()
    user = create_user(db, email="owner@example.com")
    create_user(db, email="taken@example.com")

    with pytest.raises(HTTPException) as exc:
        _sync_supabase_profile(
            db,
            user,
            {
                "sub": str(user.supabase_user_id),
                "email": "taken@example.com",
                "user_metadata": {"name": user.name},
            },
        )

    assert exc.value.status_code == 409


def test_get_current_user_links_pre_registered_user_by_email(monkeypatch):
    from app.core import auth

    db = build_session()
    supabase_user_id = uuid.uuid4()
    user = User(name="Invited User", email="invited@example.com")
    db.add(user)
    db.commit()

    monkeypatch.setattr(
        auth,
        "_decode_supabase_token",
        lambda token: {
            "sub": str(supabase_user_id),
            "email": "invited@example.com",
            "user_metadata": {},
        },
    )

    current_user = auth.get_current_user(
        credentials=type("Credentials", (), {"credentials": "valid-token"})(),
        db=db,
    )

    assert current_user.id == user.id
    assert current_user.supabase_user_id == supabase_user_id
    assert db.query(User).count() == 1


def test_get_current_user_rejects_unprovisioned_supabase_identity(monkeypatch):
    from app.core import auth

    db = build_session()
    supabase_user_id = uuid.uuid4()
    monkeypatch.setattr(
        auth,
        "_decode_supabase_token",
        lambda token: {
            "sub": str(supabase_user_id),
            "email": "unknown@example.com",
            "user_metadata": {"name": "Unknown"},
        },
    )

    with pytest.raises(HTTPException) as exc:
        auth.get_current_user(
            credentials=type("Credentials", (), {"credentials": "valid-token"})(),
            db=db,
        )

    assert exc.value.status_code == 403
    assert db.query(User).count() == 0
