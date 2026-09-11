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
