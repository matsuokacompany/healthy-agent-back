import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.models import Role, RoleNameEnum, User, UserRole
from app.models.schemas import RoleNameEnum as SchemaRoleNameEnum, UserCreate
from app.services import user_service as user_service_module
from app.services.user_service import UserService


def build_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def super_admin(db):
    role = Role(name=RoleNameEnum.SUPER_ADMIN.value)
    user = User(name="Super Admin", email="super@example.com")
    db.add_all([role, user])
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.commit()
    db.refresh(user)
    return user


def test_create_user_invites_supabase_when_no_identity_supplied(monkeypatch):
    db = build_session()
    admin = super_admin(db)
    invited_id = uuid.uuid4()
    monkeypatch.setattr(user_service_module, "invite_supabase_user", lambda email, name=None: invited_id)

    created = UserService(db).create_user(
        UserCreate(
            name="Dra. Ana",
            email="ana@example.com",
            roles=[SchemaRoleNameEnum.PROFESSIONAL],
        ),
        admin,
    )

    assert created.supabase_user_id == invited_id


def test_create_user_does_not_invite_when_supabase_user_id_supplied(monkeypatch):
    db = build_session()
    admin = super_admin(db)
    existing_supabase_id = uuid.uuid4()
    monkeypatch.setattr(
        user_service_module,
        "invite_supabase_user",
        lambda email, name=None: (_ for _ in ()).throw(AssertionError("should not invite when identity already linked")),
    )

    created = UserService(db).create_user(
        UserCreate(
            name="Dra. Ana",
            email="ana2@example.com",
            supabase_user_id=str(existing_supabase_id),
            roles=[SchemaRoleNameEnum.PROFESSIONAL],
        ),
        admin,
    )

    assert created.supabase_user_id == existing_supabase_id


def test_create_user_succeeds_even_if_invite_fails(monkeypatch):
    db = build_session()
    admin = super_admin(db)
    monkeypatch.setattr(user_service_module, "invite_supabase_user", lambda email, name=None: None)

    created = UserService(db).create_user(
        UserCreate(name="Paciente", email="paciente@example.com"),
        admin,
    )

    assert created.supabase_user_id is None
