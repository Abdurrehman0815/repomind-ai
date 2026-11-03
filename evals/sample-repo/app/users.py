"""In-memory user store for the sample service."""
from typing import Optional

_USERS: dict[str, dict] = {}


def find_user(username: str) -> Optional[dict]:
    """Return the stored user record, or None if the user is unknown."""
    return _USERS.get(username)


def add_user(username: str, salt: str, password_hash: str) -> None:
    """Register a user with a pre-computed password hash."""
    _USERS[username] = {"salt": salt, "password_hash": password_hash, "failed_attempts": 0}
