"""Entry point: a tiny CLI that logs a user in."""
import sys

from app.auth import login


def main() -> int:
    username, password = sys.argv[1], sys.argv[2]
    print("welcome" if login(username, password) else "access denied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
