import pytest
from fastapi import HTTPException

from app.models.models import Role, RoleNameEnum, User
from app.services.patient_dashboard_service import PatientDashboardService


def user_with_roles(*roles: RoleNameEnum) -> User:
    user = User(id=10, name="Teste", email="teste@example.com")
    user.role_records = [Role(name=role.value) for role in roles]
    return user


def test_super_admin_can_access_patient_dashboard_without_patient_role():
    user = user_with_roles(RoleNameEnum.SUPER_ADMIN)

    PatientDashboardService._ensure_patient_access(user)


def test_super_admin_can_access_patient_dashboard_with_all_roles():
    user = user_with_roles(
        RoleNameEnum.SUPER_ADMIN,
        RoleNameEnum.ADMIN,
        RoleNameEnum.PROFESSIONAL,
        RoleNameEnum.PATIENT,
    )

    PatientDashboardService._ensure_patient_access(user)


@pytest.mark.parametrize("role", [RoleNameEnum.ADMIN, RoleNameEnum.PROFESSIONAL])
def test_non_super_admin_privileged_roles_cannot_access_patient_dashboard(role):
    user = user_with_roles(RoleNameEnum.PATIENT, role)

    with pytest.raises(HTTPException, match="Patient dashboard is only available for patient users") as exc_info:
        PatientDashboardService._ensure_patient_access(user)

    assert exc_info.value.status_code == 403


def test_patient_can_access_patient_dashboard():
    user = user_with_roles(RoleNameEnum.PATIENT)

    PatientDashboardService._ensure_patient_access(user)
