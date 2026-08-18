from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.schema import CreateTable

from app.models.models import User


def test_users_table_uuid_compiles_for_sqlite_and_postgresql():
    sqlite_sql = str(CreateTable(User.__table__).compile(dialect=sqlite.dialect()))
    postgres_sql = str(CreateTable(User.__table__).compile(dialect=postgresql.dialect()))

    assert "supabase_user_id CHAR(32)" in sqlite_sql
    assert "supabase_user_id UUID" in postgres_sql
