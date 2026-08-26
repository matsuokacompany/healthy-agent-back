"""Brazilian mobile phone number validation.

WhatsApp check-in delivery depends entirely on User.phone being a real,
deliverable Brazilian mobile number — there's no free/reliable API to check
whether a number is actually reachable on WhatsApp before sending (unlike
CNPJ's Receita Federal lookup), so this validates structure instead: a valid
DDD (area code) from ANATEL's official list, and the post-2016 8th/9th-digit
mobile format (9 digits, starting with 9).

Normalization always keeps the leading "55" country code, matching the
format User.phone is stored in everywhere else in the app (e.g. sent
directly as the WhatsApp Cloud API recipient id in whatsapp_channel.py) —
stripping it here would silently break message delivery.
"""

VALID_DDDS = {
    11, 12, 13, 14, 15, 16, 17, 18, 19,
    21, 22, 24, 27, 28,
    31, 32, 33, 34, 35, 37, 38,
    41, 42, 43, 44, 45, 46, 47, 48, 49,
    51, 53, 54, 55,
    61, 62, 63, 64, 65, 66, 67, 68, 69,
    71, 73, 74, 75, 77, 79,
    81, 82, 83, 84, 85, 86, 87, 88, 89,
    91, 92, 93, 94, 95, 96, 97, 98, 99,
}


def only_digits(value: str) -> str:
    return "".join(character for character in value if character.isdigit())


def normalize_brazilian_mobile(value: str) -> str:
    """Digits only, always with the leading "55" country code — adds it if
    the input was given as just the 11-digit local number."""
    digits = only_digits(value)
    if len(digits) == 11:
        return "55" + digits
    return digits


def is_valid_brazilian_mobile(digits: str) -> bool:
    """digits must already be normalized (see normalize_brazilian_mobile) —
    "55" + 2-digit DDD + 9-digit mobile number starting with 9 (13 digits total)."""
    if len(digits) != 13 or not digits.startswith("55"):
        return False
    local = digits[2:]
    try:
        ddd = int(local[:2])
    except ValueError:
        return False
    if ddd not in VALID_DDDS:
        return False
    return local[2] == "9"
