"""
auth.py
-------
Lightweight authentication using ONLY Python's standard library — no
bcrypt or passlib. Those libraries have C extensions that need a
compiler toolchain, which is exactly the class of problem that broke
Pillow earlier on Python 3.14 on Windows. Salted SHA-256 is not as
strong as bcrypt for a real production system, but for a hackathon
demo login it's perfectly adequate and installs with zero friction.

If you ever take this to production, swap this file for passlib/bcrypt
and don't look back — this is a "ship the demo reliably" choice, not
a "this is how real auth should work" one.
"""

import hashlib
import hmac
import secrets


def hash_password(password: str, salt: str = None) -> tuple:
    """Returns (digest, salt). Pass an existing salt to verify a login attempt."""
    salt = salt or secrets.token_hex(16)
    digest = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return digest, salt


def verify_password(password: str, stored_digest: str, salt: str) -> bool:
    """Constant-time comparison — avoids leaking timing information about the password."""
    check_digest, _ = hash_password(password, salt)
    return hmac.compare_digest(check_digest, stored_digest)


def generate_token() -> str:
    """A random, unguessable session token — this is what gets stored in the cookie."""
    return secrets.token_hex(32)


def generate_patient_id() -> str:
    """Short, friendly ID for a newly self-registered patient, e.g. P4821."""
    return "P" + str(secrets.randbelow(9000) + 1000)


def validate_abha(abha_input: str) -> bool:
    """
    Validates either a 14-digit ABHA number (with or without hyphens)
    or an ABHA address ending in @abdm or @sbx.
    """
    if not abha_input:
        return False
    cleaned = abha_input.replace("-", "").strip()
    if cleaned.isdigit() and len(cleaned) == 14:
        return True
    if "@" in abha_input and (abha_input.endswith("@abdm") or abha_input.endswith("@sbx")):
        return True
    return False


def format_abha(abha_input: str) -> str:
    """Standardizes 14-digit ABHA numbers into XX-XXXX-XXXX-XXXX format."""
    digits = [c for c in abha_input if c.isdigit()]
    if len(digits) == 14:
        d = "".join(digits)
        return f"{d[:2]}-{d[2:6]}-{d[6:10]}-{d[10:]}"
    return abha_input.strip()


def generate_abha_id() -> str:
    """Generates a random formatted 14-digit ABHA ID for kiosk walk-in simulation."""
    p1 = f"{secrets.randbelow(90) + 10:02d}"
    p2 = f"{secrets.randbelow(9000) + 1000:04d}"
    p3 = f"{secrets.randbelow(9000) + 1000:04d}"
    p4 = f"{secrets.randbelow(9000) + 1000:04d}"
    return f"{p1}-{p2}-{p3}-{p4}"


def generate_abha_address(name: str) -> str:
    """Creates a default ABHA address from full name, e.g. rahul.sharma@abdm."""
    cleaned = "".join(c.lower() if c.isalnum() else "." for c in (name or "patient")).strip(".")
    if not cleaned:
        cleaned = "patient"
    return f"{cleaned}.{secrets.randbelow(900) + 100}@abdm"


def verify_abdm_otp(abha_or_phone: str, otp: str) -> bool:
    """
    Simulates ABDM / Aadhaar OTP verification.
    In testing/kiosk demo mode, '123456' or any valid 6-digit code is accepted.
    """
    if not otp:
        return False
    clean_otp = otp.strip()
    return len(clean_otp) == 6 and clean_otp.isdigit()

