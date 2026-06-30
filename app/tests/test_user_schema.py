from datetime import datetime, timezone
import uuid

import pytest
from pydantic import ValidationError

from app.models.schemas import UserCreate, UserRead, UserUpdate


def test_user_read_accepts_uuid_supabase_user_id_and_serializes_to_string():
    supabase_user_id = uuid.uuid4()

    user = UserRead(
        id=1,
        name="Test User",
        email="user@example.com",
        supabase_user_id=supabase_user_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        roles=[],
    )

    assert user.supabase_user_id == supabase_user_id
    assert user.model_dump(mode="json")["supabase_user_id"] == str(supabase_user_id)


def test_user_create_rejects_email_like_name():
    with pytest.raises(ValidationError):
        UserCreate(name="user@example.com", email="user@example.com")


def test_user_update_rejects_email_like_name():
    with pytest.raises(ValidationError):
        UserUpdate(name="new-name@example.com")


def test_user_update_strips_valid_name():
    payload = UserUpdate(name="  Maria Silva  ")

    assert payload.name == "Maria Silva"


def test_user_read_allows_legacy_email_like_name_without_writing():
    user = UserRead(
        id=2,
        name="legacy@example.com",
        email="legacy@example.com",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        roles=[],
    )

    assert user.name == "legacy@example.com"
