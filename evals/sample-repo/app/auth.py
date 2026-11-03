"""Authentication for the sample service."""
import hashlib
import hmac

from app.users import find_user

MAX_FAILED_ATTEMPTS = 5


def hash_password(password: str, salt: str) -> str:
    """Return the hex SHA-256 digest of salt + password."""
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def login(username: str, password: str) -> bool:
    """Check a username/password pair.

    Login fails when the user does not exist, the account is locked after
    MAX_FAILED_ATTEMPTS failed attempts, or the password hash does not match.
    """
    user = find_user(username)
    if user is None:
        return False
    if user["failed_attempts"] >= MAX_FAILED_ATTEMPTS:
        return False
    expected = hash_password(password, user["salt"])
    if not hmac.compare_digest(expected, user["password_hash"]):
        user["failed_attempts"] += 1
        return False
    user["failed_attempts"] = 0
    return True
