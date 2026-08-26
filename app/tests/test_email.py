from app.core import email as email_module
from app.core.config import settings


def configure_smtp(monkeypatch, **overrides):
    values = {
        "SMTP_HOST": "smtp.hostinger.com",
        "SMTP_PORT": 465,
        "SMTP_USER": "contato@julha.com.br",
        "SMTP_PASSWORD": "s3nh@-com-arroba",
        "SMTP_FROM_EMAIL": "contato@julha.com.br",
    }
    values.update(overrides)
    for key, value in values.items():
        monkeypatch.setattr(settings, key, value)


class FakeSmtpSsl:
    instances = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.logged_in = None
        self.sent = None
        FakeSmtpSsl.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def login(self, user, password):
        self.logged_in = (user, password)

    def send_message(self, message):
        self.sent = message


def test_is_configured_requires_all_fields(monkeypatch):
    configure_smtp(monkeypatch, SMTP_PASSWORD=None)
    assert email_module.is_configured() is False

    configure_smtp(monkeypatch)
    assert email_module.is_configured() is True


def test_send_email_skips_when_not_configured(monkeypatch):
    configure_smtp(monkeypatch, SMTP_HOST=None)

    result = email_module.send_email(to="patient@example.com", subject="Oi", body="Corpo")

    assert result is False


def test_send_email_sends_via_smtp_ssl(monkeypatch):
    configure_smtp(monkeypatch)
    FakeSmtpSsl.instances = []
    monkeypatch.setattr(email_module.smtplib, "SMTP_SSL", FakeSmtpSsl)

    result = email_module.send_email(to="patient@example.com", subject="Pedido de vínculo", body="Corpo do e-mail")

    assert result is True
    assert len(FakeSmtpSsl.instances) == 1
    client = FakeSmtpSsl.instances[0]
    assert client.host == "smtp.hostinger.com"
    assert client.port == 465
    assert client.logged_in == ("contato@julha.com.br", "s3nh@-com-arroba")
    assert client.sent["To"] == "patient@example.com"
    assert client.sent["Subject"] == "Pedido de vínculo"
    assert client.sent["From"] == "contato@julha.com.br"


def test_send_email_returns_false_on_smtp_error(monkeypatch):
    configure_smtp(monkeypatch)

    class RaisingSmtpSsl:
        def __init__(self, *args, **kwargs):
            raise OSError("connection refused")

    monkeypatch.setattr(email_module.smtplib, "SMTP_SSL", RaisingSmtpSsl)

    result = email_module.send_email(to="patient@example.com", subject="Oi", body="Corpo")

    assert result is False
