from uuid import UUID

from sqlalchemy import event, text
from sqlalchemy.orm import Session


def _is_postgresql(db: Session) -> bool:
    return db.get_bind().dialect.name == "postgresql"


@event.listens_for(Session, "after_begin")
def _restore_security_context(db: Session, _transaction, connection) -> None:
    """Reapply transaction-local context after commit/rollback on pooled sessions."""
    if connection.dialect.name != "postgresql":
        return
    supabase_user_id = db.info.get("supabase_user_id")
    user_email = db.info.get("user_email")
    service_context = db.info.get("service_context")
    if supabase_user_id:
        connection.execute(
            text("SELECT set_config('app.supabase_user_id', :user_id, true)"),
            {"user_id": supabase_user_id},
        )
    if user_email:
        connection.execute(text("SELECT set_config('app.user_email', :email, true)"), {"email": user_email})
    if service_context:
        connection.execute(
            text("SELECT set_config('app.service_context', :service_name, true)"),
            {"service_name": service_context},
        )


def set_database_identity_context(db: Session, supabase_user_id: UUID, email: str | None = None) -> None:
    """Bind a verified external identity to the current database transaction."""
    if not _is_postgresql(db):
        return
    db.info["supabase_user_id"] = str(supabase_user_id)
    db.info["user_email"] = email
    db.execute(
        text("SELECT set_config('app.supabase_user_id', :user_id, true)"),
        {"user_id": str(supabase_user_id)},
    )
    if email:
        db.execute(text("SELECT set_config('app.user_email', :email, true)"), {"email": email})


def set_database_service_context(db: Session, service_name: str) -> None:
    """Authorize a trusted background transaction without impersonating a user."""
    if not _is_postgresql(db):
        return
    db.info["service_context"] = service_name
    db.execute(text("SELECT set_config('app.service_context', :service_name, true)"), {"service_name": service_name})
