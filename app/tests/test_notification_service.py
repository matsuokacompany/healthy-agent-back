from datetime import date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.models import (
    MonitoringPlan,
    MonitoringProfessional,
    Notification,
    NotificationKindEnum,
    ProfessionalProfile,
    User,
)
from app.services.notification_service import (
    assigned_professional_user_ids,
    notify_ai_report_ready,
    notify_checkin_pending,
    notify_patient_assigned,
    notify_symptom_reported,
)


def build_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def make_user(db, name="Usuário"):
    user = User(name=name, email=f"{name.lower()}-{datetime.now().timestamp()}@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def link_professional(db, patient_id, *, active=True, plan_active=True):
    professional_user = make_user(db, name="Profissional")
    profile = ProfessionalProfile(user_id=professional_user.id, active=True)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    plan = MonitoringPlan(patient_id=patient_id, title="Plano", active=plan_active, start_date=date.today())
    db.add(plan)
    db.commit()
    db.refresh(plan)
    db.add(
        MonitoringProfessional(
            monitoring_plan_id=plan.id,
            professional_profile_id=profile.id,
            role="responsável",
            active=active,
        )
    )
    db.commit()
    return professional_user


def test_assigned_professional_user_ids_returns_active_links_only():
    db = build_session()
    patient = make_user(db, name="Paciente")
    active_pro = link_professional(db, patient.id, active=True)
    link_professional(db, patient.id, active=False)  # inactive link, must be excluded
    link_professional(db, patient.id, plan_active=False)  # inactive plan, must be excluded

    result = assigned_professional_user_ids(db, patient.id)

    assert result == [active_pro.id]


def test_assigned_professional_user_ids_excludes_given_user():
    db = build_session()
    patient = make_user(db, name="Paciente")
    pro_a = link_professional(db, patient.id)
    pro_b = link_professional(db, patient.id)

    result = assigned_professional_user_ids(db, patient.id, exclude_user_id=pro_a.id)

    assert result == [pro_b.id]


def test_notify_ai_report_ready_does_not_notify_the_requester():
    db = build_session()
    patient = make_user(db, name="Paciente")
    requester = link_professional(db, patient.id)

    notify_ai_report_ready(db, patient=patient, generated_by_user_id=requester.id)
    db.commit()

    assert db.query(Notification).count() == 0


def test_notify_ai_report_ready_notifies_other_assigned_professionals():
    db = build_session()
    patient = make_user(db, name="Paciente")
    requester = link_professional(db, patient.id)
    other = link_professional(db, patient.id)

    notify_ai_report_ready(db, patient=patient, generated_by_user_id=requester.id)
    db.commit()

    notifications = db.query(Notification).all()
    assert len(notifications) == 1
    assert notifications[0].user_id == other.id
    assert notifications[0].kind == NotificationKindEnum.AI_REPORT_READY.value
    assert patient.name in notifications[0].message


def test_notify_patient_assigned_writes_expected_kind_and_message():
    db = build_session()
    patient = make_user(db, name="Paciente")
    professional = make_user(db, name="Profissional")

    notify_patient_assigned(db, professional_user_id=professional.id, patient=patient)
    db.commit()

    notification = db.query(Notification).one()
    assert notification.user_id == professional.id
    assert notification.kind == NotificationKindEnum.PATIENT_ASSIGNED.value
    assert patient.name in notification.message


def test_notify_checkin_pending_writes_expected_kind():
    db = build_session()
    patient = make_user(db, name="Paciente")

    notify_checkin_pending(db, patient_user_id=patient.id)
    db.commit()

    notification = db.query(Notification).one()
    assert notification.user_id == patient.id
    assert notification.kind == NotificationKindEnum.CHECKIN_PENDING.value


def test_notify_symptom_reported_is_a_noop_with_no_assigned_professionals():
    db = build_session()
    patient = make_user(db, name="Paciente")

    notify_symptom_reported(db, patient=patient, report=None)
    db.commit()

    assert db.query(Notification).count() == 0
