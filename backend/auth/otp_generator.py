from __future__ import annotations

import secrets


def generate_otp(length: int = 6) -> str:
    if length != 6:
        raise ValueError("OTP length must remain 6 digits")
    return f"{secrets.randbelow(1_000_000):06d}"
