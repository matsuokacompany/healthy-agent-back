import re

EMAIL_LIKE_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def is_email_like(value: str | None) -> bool:
    if not isinstance(value, str):
        return False
    return bool(EMAIL_LIKE_RE.fullmatch(value.strip()))


def validate_user_name(value: str | None) -> str:
    if not isinstance(value, str):
        raise ValueError("User name is required")
    name = value.strip()
    if not name:
        raise ValueError("User name is required")
    if is_email_like(name):
        raise ValueError("User name cannot be an email address")
    return name
