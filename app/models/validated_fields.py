from typing import Annotated

from pydantic import AfterValidator, Field


def normalize_plain_text(value: str) -> str:
    value = value.strip()
    if "\x00" in value:
        raise ValueError("NUL characters are not allowed")
    if any(ord(character) < 32 and character not in {"\n", "\r", "\t"} for character in value):
        raise ValueError("Unsupported control characters")
    return value


ShortPlainText = Annotated[
    str,
    Field(min_length=1, max_length=255),
    AfterValidator(normalize_plain_text),
]

ClinicalPlainText = Annotated[
    str,
    Field(min_length=1, max_length=20_000),
    AfterValidator(normalize_plain_text),
]
