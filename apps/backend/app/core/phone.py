from __future__ import annotations


def normalize_phone(value: str) -> str:
    digits = "".join(char for char in value if char.isdigit())

    if not digits:
        raise ValueError("Phone number must not be empty.")

    if len(digits) == 10:
        digits = f"7{digits}"
    elif len(digits) == 11 and digits.startswith("8"):
        digits = f"7{digits[1:]}"

    return f"+{digits}"
