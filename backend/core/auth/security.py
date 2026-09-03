"""Password hashing and token minting.

Deliberately stdlib-only, matching the project's "no credentials required to
run" rule — adding bcrypt/argon2 would mean a new binary dependency for every
contributor. PBKDF2-HMAC-SHA256 at the OWASP-recommended iteration count is a
sound choice for this stack.

Nothing here is ever stored in reversible form:
  - passwords  -> pbkdf2_sha256$<iterations>$<salt>$<derived key>
  - session and invite tokens -> only their SHA-256 fingerprint is persisted,
    so a leaked database cannot be replayed against the API.
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

# OWASP Password Storage Cheat Sheet (2023) for PBKDF2-HMAC-SHA256.
PBKDF2_ITERATIONS = 600_000
_ALGO = "pbkdf2_sha256"

SESSION_TTL_HOURS = 12
INVITE_TTL_HOURS = 72

PASSWORD_MIN_LENGTH = 10


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def expires_in(hours: int) -> str:
    return iso(now() + timedelta(hours=hours))


def is_expired(expires_at: str) -> bool:
    try:
        return now() >= parse_iso(expires_at)
    except (ValueError, TypeError):
        return True


def password_problem(password: str) -> Optional[str]:
    """The one strength rule shared by sign-up, invite redemption and the
    password-reset script. Returns the reason a password is rejected, or None."""
    if len(password) < PASSWORD_MIN_LENGTH:
        return f"Password must be at least {PASSWORD_MIN_LENGTH} characters."
    if password.strip() != password:
        return "Password must not start or end with whitespace."
    if password.isdigit() or password.isalpha():
        return "Password must mix letters with numbers or symbols."
    return None


def hash_password(password: str) -> str:
    """Salted PBKDF2 digest. The plaintext never leaves this function."""
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"{_ALGO}${PBKDF2_ITERATIONS}${salt.hex()}${derived.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    """Constant-time verification; any malformed hash simply fails closed."""
    try:
        algo, iterations, salt_hex, expected_hex = encoded.split("$")
        if algo != _ALGO:
            return False
        derived = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(derived.hex(), expected_hex)
    except (ValueError, AttributeError):
        return False


def new_token(nbytes: int = 32) -> str:
    """Cryptographically random, URL-safe. 32 bytes = 256 bits of entropy."""
    return secrets.token_urlsafe(nbytes)


def fingerprint(token: str) -> str:
    """What we store instead of the token itself."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


def project_id_from_name(name: str) -> str:
    """'Neon Nights' -> 'PROJ_NEON_NIGHTS'. Collisions are resolved by the store."""
    slug = "".join(ch if ch.isalnum() else "_" for ch in name.strip().upper())
    slug = "_".join(part for part in slug.split("_") if part)[:40]
    return f"PROJ_{slug or 'UNTITLED'}"
