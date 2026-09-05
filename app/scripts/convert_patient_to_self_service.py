import argparse
import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.db.security_context import set_database_service_context
from app.db.session import SessionLocal
from app.models.models import MonitoringPlan, MonitoringPlanOriginEnum, MonitoringProfessional, User

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Unlink a patient from every professional and switch them to a self-service "
            "monitoring plan. Deactivates their active PROFESSIONAL-origin MonitoringPlan(s) "
            "and MonitoringProfessional link(s), and creates (or reactivates) a SELF_SERVICE "
            "plan in their place -- the reverse of PatientLinkService.respond's accept path."
        )
    )
    parser.add_argument("--email", required=True, help="patient's email address")
    parser.add_argument(
        "--execute", action="store_true", help="apply the change (the default only reports what would happen)"
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    with SessionLocal() as db:
        set_database_service_context(db, "convert_patient_to_self_service")

        patient = db.query(User).filter(User.email == args.email).first()
        if not patient:
            print(f"No user found with email {args.email}")
            return

        professional_plans = (
            db.query(MonitoringPlan)
            .filter(
                MonitoringPlan.patient_id == patient.id,
                MonitoringPlan.origin == MonitoringPlanOriginEnum.PROFESSIONAL.value,
                MonitoringPlan.active.is_(True),
            )
            .all()
        )
        existing_self_service_plan = (
            db.query(MonitoringPlan)
            .filter(
                MonitoringPlan.patient_id == patient.id,
                MonitoringPlan.origin == MonitoringPlanOriginEnum.SELF_SERVICE.value,
                MonitoringPlan.active.is_(True),
            )
            .first()
        )

        print(f"Patient: {patient.name} <{patient.email}> (id={patient.id})")
        print(f"Active professional-origin plans to deactivate: {len(professional_plans)}")
        for plan in professional_plans:
            active_links = [link for link in plan.professional_links if link.active]
            print(f"  - plan #{plan.id} ({plan.title!r}), {len(active_links)} active professional link(s)")
        if existing_self_service_plan:
            print(f"Already has an active self-service plan (#{existing_self_service_plan.id}) -- will be left as-is")
        else:
            print("Will create a new active SELF_SERVICE plan")

        if not args.execute:
            print("\nDry run only; pass --execute to apply the change.")
            return

        for plan in professional_plans:
            db.query(MonitoringProfessional).filter(
                MonitoringProfessional.monitoring_plan_id == plan.id,
                MonitoringProfessional.active.is_(True),
            ).update({"active": False})
            plan.active = False

        if not existing_self_service_plan:
            db.add(
                MonitoringPlan(
                    patient_id=patient.id,
                    title="Automonitoramento",
                    active=True,
                    start_date=datetime.now(ZoneInfo(settings.SCHEDULER_TIMEZONE)).date(),
                    origin=MonitoringPlanOriginEnum.SELF_SERVICE.value,
                )
            )

        db.commit()
        print(f"\nDone: {patient.email} is now self-service only.")


if __name__ == "__main__":
    main()
