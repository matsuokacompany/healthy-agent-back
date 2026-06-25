from datetime import datetime, timezone
import uuid

from app.models.schemas import UserRead


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
