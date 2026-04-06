# src/uid.py
import re
from ulid import ULID

_ULID_PATTERN = re.compile(r"^[0-9A-Z]{26}$")


def new_ulid() -> str:
    """Return a new ULID as an uppercase 26-character string."""
    return str(ULID())


def is_valid_ulid(value: str) -> bool:
    return bool(_ULID_PATTERN.match(value))
