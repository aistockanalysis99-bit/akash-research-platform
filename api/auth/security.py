"""JWT creation + verification.

SECRET_KEY comes from the environment. If it is unset we fall back to a
process-random key so login still WORKS (no 500s), but tokens then reset on
every restart — a loud warning is logged telling the operator to set a
stable SECRET_KEY in the Render/host env.
"""
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt

log = logging.getLogger(__name__)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    SECRET_KEY = secrets.token_urlsafe(48)
    log.warning(
        "auth: SECRET_KEY is not set — using a process-random key. Logins "
        "work, but every restart invalidates all sessions. Set a stable "
        "SECRET_KEY in the server environment for persistent sessions.")


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """Return the token's claims if valid + unexpired, else None. Ready to
    back a FastAPI dependency when API routes are put behind auth."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
