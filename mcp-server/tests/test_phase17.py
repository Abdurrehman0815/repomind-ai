"""
RepoMind AI — MCP Server Tests Entrypoint
"""
import sys
from pathlib import Path

# Add backend and mcp-server to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
MCP_SERVER_DIR = REPO_ROOT / "mcp-server"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(MCP_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_SERVER_DIR))

# Import all tests from backend/tests/unit/test_phase17.py
from tests.unit.test_phase17 import (  # noqa: E402
    TestSecurityControls,
    TestRepoTools,
    TestGitTools,
    TestExecutionTools,
    TestFastMCPServerIntegration,
    sample_repo,
    indexed_project,
)

__all__ = [
    "TestSecurityControls",
    "TestRepoTools",
    "TestGitTools",
    "TestExecutionTools",
    "TestFastMCPServerIntegration",
    "sample_repo",
    "indexed_project",
]
