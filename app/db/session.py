import re

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args={
        "connect_timeout": 5
    }
)

if settings.DATABASE_RUNTIME_ROLE:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", settings.DATABASE_RUNTIME_ROLE):
        raise RuntimeError("DATABASE_RUNTIME_ROLE contains unsupported characters")

    @event.listens_for(engine, "connect")
    def _set_runtime_role(dbapi_connection, _connection_record):
        if engine.dialect.name != "postgresql":
            return
        with dbapi_connection.cursor() as cursor:
            cursor.execute(f'SET ROLE "{settings.DATABASE_RUNTIME_ROLE}"')

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)
