"""User lookup + password verification against api/auth/users.json.

Passwords are stored as bcrypt hashes (never plaintext). authenticate_user
does a constant-time hash compare — a wrong email and a wrong password are
indistinguishable to a caller, and a malformed/legacy row can never
accidentally authenticate.
"""
import json
import logging
from pathlib import Path

import bcrypt

log = logging.getLogger(__name__)

USERS_FILE = Path(__file__).parent / "users.json"


def get_users() -> list[dict]:
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, ValueError) as e:
        log.error("auth: could not read users file: %s", e)
        return []


def authenticate_user(email: str, password: str):
    """Return the user dict on a correct email+password, else None."""
    if not email or not password:
        return None
    for user in get_users():
        if user.get("email") != email:
            continue
        stored = user.get("password") or ""
        if not stored.startswith("$2"):
            # Not a bcrypt hash — refuse rather than fall back to plaintext.
            log.error("auth: user %s has a non-hashed password; refusing", email)
            return None
        try:
            if bcrypt.checkpw(password.encode(), stored.encode()):
                return user
        except ValueError:
            return None
    return None
