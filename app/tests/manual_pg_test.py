from app.db.base import engine
from sqlalchemy import text

def test_pg_connection():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT version();"))
        version = result.scalar()
        print("\nPostgreSQL conectado com sucesso ✅ ->", version)
        assert "PostgreSQL" in version
