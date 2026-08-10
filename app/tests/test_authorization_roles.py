import pytest
from fastapi import HTTPException

from app.core.permissions import can_access_user, has_role, is_admin, is_super_admin
from app.models.models import Role, RoleNameEnum, User
from app.services.professional_service import ProfessionalService


def user_with_roles(*roles):
    user = User(id=10, name="Teste", email="teste@example.com")
    user.role_records = [Role(name=role.value if isinstance(role, RoleNameEnum) else role) for role in roles]
    return user


def test_super_admin_has_admin_privileges_without_hardcoded_identity():
    user = user_with_roles(RoleNameEnum.SUPER_ADMIN)

    assert is_super_admin(user) is True
    assert is_admin(user) is True
    assert can_access_user(user, target_user_id=999) is True


def test_admin_can_access_other_users_but_is_not_super_admin():
    user = user_with_roles(RoleNameEnum.ADMIN)

    assert is_super_admin(user) is False
    assert is_admin(user) is True
    assert can_access_user(user, target_user_id=999) is True


def test_patient_without_admin_role_can_only_access_self():
    user = user_with_roles(RoleNameEnum.PATIENT)
    user.id = 123

    assert has_role(user, RoleNameEnum.PATIENT) is True
    assert is_admin(user) is False
    assert can_access_user(user, target_user_id=123) is True
    assert can_access_user(user, target_user_id=999) is False


@pytest.mark.parametrize("role", [RoleNameEnum.ADMIN, RoleNameEnum.SUPER_ADMIN, RoleNameEnum.PROFESSIONAL])
def test_report_tools_accept_administrative_and_professional_roles(role):
    ProfessionalService._require_report_role(user_with_roles(role))


def test_report_tools_reject_patient_role_alone():
    with pytest.raises(HTTPException) as exc_info:
        ProfessionalService._require_report_role(user_with_roles(RoleNameEnum.PATIENT))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Insufficient role"
