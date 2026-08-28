from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base_class import Base
from app.models.models import (
    AiReportCache,
    AiReportStatusEnum,
    CheckTypeEnum,
    DailyReport,
    DailyReportStatusEnum,
    MonitoringPlan,
    MonitoringPlanOriginEnum,
    ProfessionalProfile,
    Role,
    RoleNameEnum,
    Subscription,
    SubscriptionStatusEnum,
    User,
    UserRole,
)
from app.models.schemas import AdminCostEntryCreate, AdminUserStatusEnum
from app.services.admin_reporting_service import AdminReportingService


def build_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _role(db, name):
    role = db.query(Role).filter(Role.name == name).first()
    if not role:
        role = Role(name=name)
        db.add(role)
        db.flush()
    return role


def create_patient(db, *, email, active_plan):
    user = User(name="Paciente", email=email)
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=_role(db, RoleNameEnum.PATIENT.value).id))
    if active_plan:
        db.add(MonitoringPlan(patient_id=user.id, title="Plano", active=True, origin=MonitoringPlanOriginEnum.PROFESSIONAL.value))
    db.commit()
    db.refresh(user)
    return user


def create_professional(db, *, email, active_profile):
    user = User(name="Profissional", email=email)
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=_role(db, RoleNameEnum.PROFESSIONAL.value).id))
    db.add(ProfessionalProfile(user_id=user.id, active=active_profile))
    db.commit()
    db.refresh(user)
    return user


def create_admin(db, *, email):
    user = User(name="Admin", email=email)
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=_role(db, RoleNameEnum.SUPER_ADMIN.value).id))
    db.commit()
    db.refresh(user)
    return user


def test_list_users_computes_active_status_per_role():
    db = build_session()
    active_patient = create_patient(db, email="ativo@example.com", active_plan=True)
    inactive_patient = create_patient(db, email="inativo@example.com", active_plan=False)
    active_pro = create_professional(db, email="pro-ativo@example.com", active_profile=True)
    inactive_pro = create_professional(db, email="pro-inativo@example.com", active_profile=False)
    admin = create_admin(db, email="admin@example.com")

    users = {u.email: u for u in AdminReportingService(db).list_users()}

    assert users[active_patient.email].status == AdminUserStatusEnum.ACTIVE
    assert users[inactive_patient.email].status == AdminUserStatusEnum.INACTIVE
    assert users[active_pro.email].status == AdminUserStatusEnum.ACTIVE
    assert users[inactive_pro.email].status == AdminUserStatusEnum.INACTIVE
    assert users[admin.email].status == AdminUserStatusEnum.ACTIVE


def test_list_users_filters_by_role_status_and_search():
    db = build_session()
    create_patient(db, email="maria@example.com", active_plan=True)
    create_patient(db, email="joao@example.com", active_plan=False)
    create_professional(db, email="dra.ana@example.com", active_profile=True)

    service = AdminReportingService(db)

    only_patients = service.list_users(role=RoleNameEnum.PATIENT.value)
    assert {u.email for u in only_patients} == {"maria@example.com", "joao@example.com"}

    only_active = service.list_users(status=AdminUserStatusEnum.ACTIVE)
    assert {u.email for u in only_active} == {"maria@example.com", "dra.ana@example.com"}

    search_result = service.list_users(search="maria")
    assert [u.email for u in search_result] == ["maria@example.com"]

    search_by_email_fragment = service.list_users(search="ana@example")
    assert [u.email for u in search_by_email_fragment] == ["dra.ana@example.com"]


def _create_completed_ai_report(db, *, patient, professional, generated_at, actual_cost):
    report = AiReportCache(
        patient_id=patient.id,
        professional_user_id=professional.id,
        periodo="personalizado",
        modo="avaliacao_clinica",
        status=AiReportStatusEnum.COMPLETED.value,
        generated_at=generated_at,
        actual_cost=actual_cost,
    )
    db.add(report)
    db.commit()
    return report


def _create_sent_daily_report(db, *, user, plan, report_date, prompt_sent_at):
    report = DailyReport(
        user_id=user.id,
        monitoring_plan_id=plan.id,
        report_date=report_date,
        check_type=CheckTypeEnum.MORNING,
        status=DailyReportStatusEnum.COMPLETED,
        completed=True,
        awaiting_response=False,
        awaiting_cause=False,
        prompt_sent_at=prompt_sent_at,
        expires_at=prompt_sent_at + timedelta(hours=24),
    )
    db.add(report)
    db.commit()
    return report


def test_cost_summary_aggregates_ai_reports_and_whatsapp_messages(monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_COST_PER_MESSAGE_CENTS", 25)
    db = build_session()
    patient = create_patient(db, email="paciente@example.com", active_plan=True)
    professional = create_professional(db, email="pro@example.com", active_profile=True)
    plan = db.query(MonitoringPlan).filter(MonitoringPlan.patient_id == patient.id).one()

    today = datetime.now(timezone.utc)
    _create_completed_ai_report(db, patient=patient, professional=professional, generated_at=today, actual_cost=0.015)
    _create_completed_ai_report(db, patient=patient, professional=professional, generated_at=today - timedelta(days=1), actual_cost=0.02)
    # Outside the (default month-to-date) range if it's from last month — use an explicit range instead to be deterministic.
    _create_sent_daily_report(db, user=patient, plan=plan, report_date=today.date(), prompt_sent_at=today)
    _create_sent_daily_report(db, user=patient, plan=plan, report_date=(today - timedelta(days=1)).date(), prompt_sent_at=today - timedelta(days=1))

    start = (today - timedelta(days=2)).date()
    end = today.date()
    summary = AdminReportingService(db).cost_summary(start_date=start, end_date=end)

    assert summary.ai_report_count == 2
    assert summary.ai_report_cost_usd == 0.04
    assert summary.whatsapp_message_count == 2
    assert summary.whatsapp_cost_per_message_cents == 25
    assert summary.whatsapp_cost_cents == 50


def test_cost_summary_supports_fractional_cost_per_message(monkeypatch):
    # Real per-message WhatsApp cost is usually well under one cent (most
    # traffic falls inside Meta's free service-conversation window) — the
    # setting must be a float, not an int, or this always rounds to 0.
    monkeypatch.setattr(settings, "WHATSAPP_COST_PER_MESSAGE_CENTS", 0.073)
    db = build_session()
    patient = create_patient(db, email="paciente@example.com", active_plan=True)
    plan = db.query(MonitoringPlan).filter(MonitoringPlan.patient_id == patient.id).one()

    today = datetime.now(timezone.utc)
    _create_sent_daily_report(db, user=patient, plan=plan, report_date=today.date(), prompt_sent_at=today)

    start = today.date()
    end = today.date()
    summary = AdminReportingService(db).cost_summary(start_date=start, end_date=end)

    assert summary.whatsapp_message_count == 1
    assert summary.whatsapp_cost_per_message_cents == 0.073
    assert summary.whatsapp_cost_cents == pytest.approx(0.073)


def test_cost_summary_leaves_whatsapp_cost_unset_when_rate_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_COST_PER_MESSAGE_CENTS", None)
    db = build_session()
    patient = create_patient(db, email="paciente@example.com", active_plan=True)
    plan = db.query(MonitoringPlan).filter(MonitoringPlan.patient_id == patient.id).one()
    today = datetime.now(timezone.utc)
    _create_sent_daily_report(db, user=patient, plan=plan, report_date=today.date(), prompt_sent_at=today)

    summary = AdminReportingService(db).cost_summary(start_date=today.date(), end_date=today.date())

    assert summary.whatsapp_message_count == 1
    assert summary.whatsapp_cost_per_message_cents is None
    assert summary.whatsapp_cost_cents is None


def test_whatsapp_stats_builds_daily_series_with_zero_filled_gaps(monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_COST_PER_MESSAGE_CENTS", 10)
    db = build_session()
    patient = create_patient(db, email="paciente@example.com", active_plan=True)
    plan = db.query(MonitoringPlan).filter(MonitoringPlan.patient_id == patient.id).one()
    today = datetime.now(timezone.utc)
    _create_sent_daily_report(db, user=patient, plan=plan, report_date=today.date(), prompt_sent_at=today)
    _create_sent_daily_report(db, user=patient, plan=plan, report_date=(today - timedelta(days=2)).date(), prompt_sent_at=today - timedelta(days=2))

    stats = AdminReportingService(db).whatsapp_stats(days=5)

    assert stats.period_days == 5
    assert len(stats.daily) == 5
    assert stats.total_sent == 2
    assert stats.cost_per_message_cents == 10
    assert stats.estimated_cost_cents == 20
    by_date = {point.date: point.sent_count for point in stats.daily}
    assert by_date[today.date()] == 1
    assert by_date[(today - timedelta(days=2)).date()] == 1
    assert by_date[(today - timedelta(days=1)).date()] == 0


def test_create_list_and_delete_cost_entry():
    db = build_session()
    admin = create_admin(db, email="admin@example.com")
    service = AdminReportingService(db)

    created = service.create_cost_entry(
        admin,
        AdminCostEntryCreate(description="Contrato de suporte", category="Operações", amount_cents=15000, incurred_on=date(2026, 8, 1)),
    )
    assert created.created_by_user_id == admin.id

    entries = service.list_cost_entries(start_date=date(2026, 8, 1), end_date=date(2026, 8, 31))
    assert len(entries) == 1
    assert entries[0].description == "Contrato de suporte"

    outside_range = service.list_cost_entries(start_date=date(2026, 9, 1), end_date=date(2026, 9, 30))
    assert outside_range == []

    service.delete_cost_entry(created.id)
    assert service.list_cost_entries() == []


def test_delete_cost_entry_raises_404_when_missing():
    db = build_session()

    with pytest.raises(HTTPException) as exc:
        AdminReportingService(db).delete_cost_entry(999)

    assert exc.value.status_code == 404


def test_cost_summary_includes_manual_cost_entries():
    db = build_session()
    admin = create_admin(db, email="admin@example.com")
    service = AdminReportingService(db)
    service.create_cost_entry(
        admin,
        AdminCostEntryCreate(description="Infra", category="Tecnologia", amount_cents=5000, incurred_on=date(2026, 8, 10)),
    )
    service.create_cost_entry(
        admin,
        AdminCostEntryCreate(description="Fora do período", category=None, amount_cents=9999, incurred_on=date(2026, 1, 1)),
    )

    summary = service.cost_summary(start_date=date(2026, 8, 1), end_date=date(2026, 8, 31))

    assert summary.manual_cost_total_cents == 5000
    assert len(summary.manual_cost_entries) == 1
    assert summary.manual_cost_entries[0].description == "Infra"


def test_billing_summary_computes_mrr_from_active_subscriptions(monkeypatch):
    monkeypatch.setattr(settings, "ASAAS_SELF_MONITORING_PRICE_CENTS", 2990)
    monkeypatch.setattr(settings, "ASAAS_SELF_MONITORING_SEMIANNUAL_PRICE_CENTS", 9990)
    monkeypatch.setattr(settings, "ASAAS_PROFESSIONAL_MONTHLY_PRICE_CENTS", 3990)
    db = build_session()
    patient_monthly = create_patient(db, email="patient-monthly@example.com", active_plan=False)
    patient_semiannual = create_patient(db, email="patient-semiannual@example.com", active_plan=False)
    professional = create_professional(db, email="professional@example.com", active_profile=True)

    db.add_all([
        Subscription(user_id=patient_monthly.id, status=SubscriptionStatusEnum.ACTIVE.value, plan_id="monthly"),
        Subscription(user_id=patient_semiannual.id, status=SubscriptionStatusEnum.ACTIVE.value, plan_id="semiannual"),
        Subscription(user_id=professional.id, status=SubscriptionStatusEnum.ACTIVE.value, plan_id="monthly"),
    ])
    db.commit()

    summary = AdminReportingService(db).billing_summary()

    # 2990 (patient monthly) + 9990/6=1665 (patient semiannual) + 3990 (professional monthly)
    assert summary.mrr_cents == 2990 + 1665 + 3990
    assert summary.active_subscriptions == 3


def test_billing_summary_counts_trialing_and_past_due():
    db = build_session()
    patient_a = create_patient(db, email="a@example.com", active_plan=False)
    patient_b = create_patient(db, email="b@example.com", active_plan=False)
    db.add_all([
        Subscription(user_id=patient_a.id, status=SubscriptionStatusEnum.TRIALING.value),
        Subscription(user_id=patient_b.id, status=SubscriptionStatusEnum.PAST_DUE.value),
    ])
    db.commit()

    summary = AdminReportingService(db).billing_summary()

    assert summary.trialing_subscriptions == 1
    assert summary.past_due_subscriptions == 1
    assert summary.mrr_cents == 0


def test_billing_summary_churn_rate_from_recent_cancellations():
    db = build_session()
    active_patient = create_patient(db, email="active@example.com", active_plan=False)
    canceled_patient = create_patient(db, email="canceled@example.com", active_plan=False)
    db.add(Subscription(user_id=active_patient.id, status=SubscriptionStatusEnum.ACTIVE.value, plan_id="monthly"))
    db.add(
        Subscription(
            user_id=canceled_patient.id,
            status=SubscriptionStatusEnum.CANCELED.value,
            updated_at=datetime.now(timezone.utc) - timedelta(days=5),
        )
    )
    db.commit()

    summary = AdminReportingService(db).billing_summary()

    assert summary.canceled_last_30d == 1
    assert summary.churn_rate == 0.5


def test_billing_summary_ignores_cancellations_older_than_30_days():
    db = build_session()
    canceled_patient = create_patient(db, email="canceled@example.com", active_plan=False)
    db.add(
        Subscription(
            user_id=canceled_patient.id,
            status=SubscriptionStatusEnum.CANCELED.value,
            updated_at=datetime.now(timezone.utc) - timedelta(days=45),
        )
    )
    db.commit()

    summary = AdminReportingService(db).billing_summary()

    assert summary.canceled_last_30d == 0
    assert summary.churn_rate == 0.0
