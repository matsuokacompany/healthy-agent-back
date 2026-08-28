"""Billing lifecycle reminders (dunning): payment overdue, trial ending soon,
access ending soon after a self-service cancellation.

Email is the only channel today (see app/core/email.py) -- deliberately not
WhatsApp, which has a real per-message cost this app otherwise goes out of
its way to minimize (see README "Otimização de custo do WhatsApp"). Each
reminder also writes a Notification row so it shows up in-app regardless of
whether the email actually sent (SMTP is best-effort, see is_configured()).
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.email import send_email
from app.db.security_context import set_database_service_context
from app.models.models import Notification, NotificationKindEnum, Subscription, SubscriptionStatusEnum, User

logger = logging.getLogger(__name__)

# How many days ahead of the deadline to warn the user, for both the trial
# and the post-cancellation access-ending reminders.
REMINDER_WINDOW_DAYS = 3


def _create_notification(db: Session, *, user_id: int, kind: NotificationKindEnum, message: str) -> None:
    db.add(Notification(user_id=user_id, kind=kind.value, message=message))


def notify_payment_overdue(db: Session, subscription: Subscription, user: User) -> None:
    """Called from the Asaas webhook the moment a subscription's status
    flips to PAST_DUE. The caller is responsible for only calling this on
    the actual transition (not on every webhook retry) to avoid spamming."""
    message = (
        "Não conseguimos confirmar o pagamento da sua assinatura Julha. "
        "Acesse a plataforma para regularizar e evitar a suspensão do acesso."
    )
    _create_notification(db, user_id=user.id, kind=NotificationKindEnum.PAYMENT_OVERDUE, message=message)
    send_email(
        to=user.email,
        subject="Pagamento pendente na sua assinatura Julha",
        body=(
            f"Olá, {user.name}!\n\n"
            "Não conseguimos confirmar o pagamento da sua assinatura Julha. "
            "Para evitar a suspensão do acesso, entre na plataforma e regularize o pagamento assim que possível.\n\n"
            "Se você já pagou, pode ser só uma questão de tempo até a confirmação do banco -- nesse caso, "
            "pode ignorar este aviso.\n\n"
            "Equipe Julha"
        ),
    )


class DunningService:
    def __init__(self, db: Session):
        self.db = db

    def run_daily_reminders(self) -> dict[str, int]:
        set_database_service_context(self.db, "dunning_scheduler")
        trial_count = self._send_trial_ending_reminders()
        access_count = self._send_access_ending_reminders()
        self.db.commit()
        return {"trial_ending": trial_count, "access_ending": access_count}

    def _send_trial_ending_reminders(self) -> int:
        now = datetime.now(timezone.utc)
        deadline = now + timedelta(days=REMINDER_WINDOW_DAYS)
        subscriptions = (
            self.db.query(Subscription)
            .filter(
                Subscription.status == SubscriptionStatusEnum.TRIALING.value,
                Subscription.trial_ends_at.isnot(None),
                Subscription.trial_ends_at <= deadline,
                Subscription.trial_ends_at > now,
                Subscription.trial_ending_reminder_sent_at.is_(None),
            )
            .all()
        )
        sent = 0
        for subscription in subscriptions:
            user = self.db.query(User).filter(User.id == subscription.user_id).first()
            if not user:
                continue
            trial_ends_at = subscription.trial_ends_at
            if trial_ends_at.tzinfo is None:
                trial_ends_at = trial_ends_at.replace(tzinfo=timezone.utc)
            days_left = max((trial_ends_at.date() - now.date()).days, 0)
            message = f"Seu período de teste na Julha termina em {days_left} dia(s). Assine para não perder o acesso."
            _create_notification(self.db, user_id=user.id, kind=NotificationKindEnum.TRIAL_ENDING, message=message)
            send_email(
                to=user.email,
                subject="Seu teste grátis na Julha está terminando",
                body=(
                    f"Olá, {user.name}!\n\n"
                    f"Seu período de teste termina em {days_left} dia(s) ({trial_ends_at.date().isoformat()}). "
                    "Para continuar com acesso à plataforma sem interrupção, escolha um plano e assine antes dessa data.\n\n"
                    "Equipe Julha"
                ),
            )
            subscription.trial_ending_reminder_sent_at = now
            sent += 1
        return sent

    def _send_access_ending_reminders(self) -> int:
        now = datetime.now(timezone.utc)
        deadline = now + timedelta(days=REMINDER_WINDOW_DAYS)
        subscriptions = (
            self.db.query(Subscription)
            .filter(
                Subscription.status == SubscriptionStatusEnum.ACTIVE.value,
                Subscription.cancel_at_period_end.is_(True),
                Subscription.current_period_end.isnot(None),
                Subscription.current_period_end <= deadline,
                Subscription.current_period_end > now,
                Subscription.access_ending_reminder_sent_at.is_(None),
            )
            .all()
        )
        sent = 0
        for subscription in subscriptions:
            user = self.db.query(User).filter(User.id == subscription.user_id).first()
            if not user:
                continue
            period_end = subscription.current_period_end
            if period_end.tzinfo is None:
                period_end = period_end.replace(tzinfo=timezone.utc)
            days_left = max((period_end.date() - now.date()).days, 0)
            message = f"Sua assinatura Julha cancelada perde o acesso em {days_left} dia(s). Reative quando quiser, direto na plataforma."
            _create_notification(self.db, user_id=user.id, kind=NotificationKindEnum.ACCESS_ENDING, message=message)
            send_email(
                to=user.email,
                subject="Seu acesso à Julha termina em breve",
                body=(
                    f"Olá, {user.name}!\n\n"
                    f"Sua assinatura foi cancelada e o acesso termina em {days_left} dia(s) ({period_end.date().isoformat()}), "
                    "quando o período já pago acaba.\n\n"
                    "Mudou de ideia? Você pode reativar a qualquer momento antes dessa data, direto na aba Assinatura da plataforma.\n\n"
                    "Equipe Julha"
                ),
            )
            subscription.access_ending_reminder_sent_at = now
            sent += 1
        return sent
