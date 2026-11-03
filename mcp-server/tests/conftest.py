"""
RepoMind AI — MCP Server test fixtures

The MCP tests reuse the backend's isolated in-memory database fixtures, so the
two suites always test the same setup. Paths are added here so the suite runs
standalone from the mcp-server directory.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
for path in (REPO_ROOT / "backend", REPO_ROOT / "mcp-server"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from tests.conftest import auto_override_get_db, test_db_session  # noqa: E402,F401
