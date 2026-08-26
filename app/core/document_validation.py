"""CPF/CNPJ format validation and CNPJ existence lookup.

CPF has no free/public registry lookup (Receita Federal only exposes that
behind paid, authenticated services) — CPF here is checksum-validated only,
same as everywhere else in Brazilian software. CNPJ has a free public lookup
(BrasilAPI, which mirrors Receita Federal's own public CNPJ data), so CNPJ
signups are checksum-validated AND confirmed to actually exist.
"""

import logging

import httpx

logger = logging.getLogger(__name__)

BRASIL_API_CNPJ_URL = "https://brasilapi.com.br/api/cnpj/v1/{cnpj}"


def only_digits(value: str) -> str:
    return "".join(character for character in value if character.isdigit())


def is_valid_cpf(digits: str) -> bool:
    if len(digits) != 11 or len(set(digits)) == 1:
        return False

    def check_digit(base: str) -> str:
        total = sum(int(digit) * weight for digit, weight in zip(base, range(len(base) + 1, 1, -1)))
        remainder = (total * 10) % 11
        return "0" if remainder == 10 else str(remainder)

    first = check_digit(digits[:9])
    second = check_digit(digits[:9] + first)
    return digits[9:] == first + second


def is_valid_cnpj(digits: str) -> bool:
    if len(digits) != 14 or len(set(digits)) == 1:
        return False

    def check_digit(base: str, weights: list[int]) -> str:
        total = sum(int(digit) * weight for digit, weight in zip(base, weights))
        remainder = total % 11
        return "0" if remainder < 2 else str(11 - remainder)

    first = check_digit(digits[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    second = check_digit(digits[:12] + first, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return digits[12:] == first + second


class CnpjLookupError(Exception):
    """The CNPJ existence lookup itself failed (network/upstream issue) —
    distinct from the CNPJ simply not being found."""


def cnpj_exists(digits: str) -> bool:
    """Whether this CNPJ is a real, registered company per Receita Federal's
    public data (via BrasilAPI). Raises CnpjLookupError on network/upstream
    failure so callers can fail closed rather than silently skip the check.
    """
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(BRASIL_API_CNPJ_URL.format(cnpj=digits))
    except httpx.HTTPError as exc:
        logger.error("CNPJ lookup failed | cnpj_suffix=%s", digits[-4:])
        raise CnpjLookupError("CNPJ lookup request failed") from exc

    if response.status_code == 404:
        return False
    if response.status_code >= 400:
        logger.error("CNPJ lookup upstream error | status=%s cnpj_suffix=%s", response.status_code, digits[-4:])
        raise CnpjLookupError(f"CNPJ lookup returned status {response.status_code}")
    return True
