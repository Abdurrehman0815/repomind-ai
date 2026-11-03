"""
RepoMind AI — Phase 3 Repository Import & Ingestion Tests

Tests:
1. Language detection and binary exclusion
2. Hash computation and line counting
3. .gitignore pattern parsing and directory pruning
4. Repository file scanning with size boundaries
5. Path traversal and forbidden root validation
6. IngestionService incremental sync (added, modified, unchanged, deleted)
7. Projects API endpoints (POST /projects, GET /projects, GET /projects/{id}, etc.)
"""
import hashlib
from pathlib import Path
import pytest
from httpx import ASGITransport, AsyncClient

from app.ingestion.scanner import (
    detect_language,
    compute_file_hash,
    count_lines_and_size,
    load_gitignore_spec,
    scan_repository,
    ScannedFileInfo,
    LANGUAGE_MAP,
)
from app.ingestion.service import (
    validate_repository_path,
    RepositoryValidationError,
    IngestionService,
    IngestionSummary,
)
from app.main import app


class TestLanguageDetectionAndHashing:
    """Verifies file type detection and cryptographic checksum calculation."""

    def test_detect_language_standard_extensions(self):
        assert detect_language(Path("main.py")) == "python"
        assert detect_language(Path("app.ts")) == "typescript"
        assert detect_language(Path("Component.tsx")) == "typescriptreact"
        assert detect_language(Path("index.js")) == "javascript"
        assert detect_language(Path("service.go")) == "go"
        assert detect_language(Path("lib.rs")) == "rust"
        assert detect_language(Path("schema.sql")) == "sql"
        assert detect_language(Path("README.md")) == "markdown"
        assert detect_language(Path("config.json")) == "json"
        assert detect_language(Path("docker-compose.yml")) == "yaml"

    def test_detect_language_explicit_filenames(self):
        assert detect_language(Path("Dockerfile")) == "dockerfile"
        assert detect_language(Path("Makefile")) == "makefile"

    def test_detect_language_ignores_binaries(self):
        assert detect_language(Path("image.png")) is None
        assert detect_language(Path("binary.exe")) is None
        assert detect_language(Path("archive.zip")) is None
        assert detect_language(Path("font.woff2")) is None

    def test_compute_file_hash(self, tmp_path: Path):
        test_file = tmp_path / "hello.py"
        content = b"print('hello world')\n"
        test_file.write_bytes(content)

        expected = hashlib.sha256(content).hexdigest()
        assert compute_file_hash(test_file) == expected

    def test_count_lines_and_size(self, tmp_path: Path):
        test_file = tmp_path / "sample.txt"
        test_file.write_text("line 1\nline 2\nline 3\n", encoding="utf-8")

        lines, size = count_lines_and_size(test_file)
        assert lines == 3
        assert size == test_file.stat().st_size


class TestRepositoryScanner:
    """Verifies filesystem traversal, gitignore adherence, and security filters."""

    def test_scanner_traverses_and_respects_gitignore(self, tmp_path: Path):
        repo = tmp_path / "test_repo"
        repo.mkdir()

        # Regular source files
        (repo / "main.py").write_text("print('main')", encoding="utf-8")
        src_dir = repo / "src"
        src_dir.mkdir()
        (src_dir / "util.ts").write_text("export const x = 1;", encoding="utf-8")

        # Ignored files and directories
        git_dir = repo / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("dummy", encoding="utf-8")

        node_dir = repo / "node_modules"
        node_dir.mkdir()
        (node_dir / "package.json").write_text("{}", encoding="utf-8")

        # Custom .gitignore
        (repo / ".gitignore").write_text("ignored_file.py\n*.tmp\n", encoding="utf-8")
        (repo / "ignored_file.py").write_text("print('secret')", encoding="utf-8")
        (repo / "temp.tmp").write_text("temp", encoding="utf-8")

        # Binary file
        (repo / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")

        results = list(scan_repository(repo))
        rel_paths = {r.relative_path for r in results}

        assert "main.py" in rel_paths
        assert "src/util.ts" in rel_paths
        assert "ignored_file.py" not in rel_paths
        assert "temp.tmp" not in rel_paths
        assert "node_modules/package.json" not in rel_paths
        assert ".git/config" not in rel_paths
        assert "logo.png" not in rel_paths

    def test_scanner_enforces_max_file_size(self, tmp_path: Path):
        repo = tmp_path / "size_repo"
        repo.mkdir()

        (repo / "small.py").write_text("x = 1\n", encoding="utf-8")
        large_file = repo / "large.py"
        large_file.write_text("x = 1\n" * 50000, encoding="utf-8")  # ~300KB

        # Set max_file_size_bytes to 1000 bytes
        results = list(scan_repository(repo, max_file_size_bytes=1000))
        rel_paths = {r.relative_path for r in results}

        assert "small.py" in rel_paths
        assert "large.py" not in rel_paths


class TestPathValidation:
    """Verifies path traversal defenses and system root exclusions."""

    def test_validate_path_valid_directory(self, tmp_path: Path):
        resolved = validate_repository_path(str(tmp_path))
        assert resolved.exists()
        assert resolved.is_dir()

    def test_validate_path_nonexistent_raises(self, tmp_path: Path):
        nonexistent = tmp_path / "does_not_exist"
        with pytest.raises(RepositoryValidationError, match="Directory does not exist"):
            validate_repository_path(str(nonexistent))

    def test_validate_path_empty_raises(self):
        with pytest.raises(RepositoryValidationError, match="cannot be empty"):
            validate_repository_path("")

    def test_validate_path_forbidden_root(self):
        with pytest.raises(RepositoryValidationError, match="Access denied: system root"):
            validate_repository_path("C:\\")


class TestIngestionServiceIncrementalSync:
    """Verifies incremental file additions, modifications, deletions, and stability."""

    @pytest.mark.asyncio
    async def test_incremental_sync_lifecycle(self, tmp_path: Path, test_db_session):
        repo_dir = tmp_path / "sync_repo"
        repo_dir.mkdir()

        file1 = repo_dir / "module_a.py"
        file1.write_text("def fn_a(): return 1\n", encoding="utf-8")

        service = IngestionService(test_db_session)
        project, summary1 = await service.import_repository(str(repo_dir), name="Sync Test Repo")

        assert project.name == "Sync Test Repo"
        assert summary1.total_scanned == 1
        assert summary1.added_files == 1

        # Second sync without changes: file should be marked unchanged
        summary2 = await service.sync_files(project)
        assert summary2.unchanged_files == 1
        assert summary2.added_files == 0
        assert summary2.modified_files == 0

        # Modify file1 and add file2
        file1.write_text("def fn_a(): return 42\n", encoding="utf-8")
        file2 = repo_dir / "module_b.py"
        file2.write_text("def fn_b(): return 'b'\n", encoding="utf-8")

        summary3 = await service.sync_files(project)
        assert summary3.modified_files == 1
        assert summary3.added_files == 1

        # Delete file1
        file1.unlink()
        summary4 = await service.sync_files(project)
        assert summary4.deleted_files == 1
        assert summary4.unchanged_files == 1


class TestProjectsAPI:
    """Verifies HTTP API endpoints for project registration, scanning, and listing."""

    @pytest.mark.asyncio
    async def test_get_projects_returns_list(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/projects")
            assert resp.status_code == 200
            data = resp.json()
            assert "projects" in data
            assert "total" in data

    @pytest.mark.asyncio
    async def test_post_project_invalid_path_returns_400(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/projects",
                json={"path": "/nonexistent/invalid/directory/path/12345"},
            )
            assert resp.status_code == 400
            assert "Directory does not exist" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_post_and_get_project_lifecycle(self, tmp_path: Path):
        repo_dir = tmp_path / "api_repo"
        repo_dir.mkdir()
        (repo_dir / "index.ts").write_text("console.log('hi')", encoding="utf-8")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Create project
            post_resp = await client.post(
                "/api/v1/projects",
                json={"path": str(repo_dir), "name": "API Test Project"},
            )
            assert post_resp.status_code == 201
            proj_data = post_resp.json()
            proj_id = proj_data["id"]
            assert proj_data["name"] == "API Test Project"
            # Scanning and embedding run as a background job after the response.
            assert proj_data["status"] == "indexing"

            # 2. Get project details
            get_resp = await client.get(f"/api/v1/projects/{proj_id}")
            assert get_resp.status_code == 200
            assert get_resp.json()["id"] == proj_id

            # 3. Trigger scan, then a re-scan sees the file as unchanged
            scan_resp = await client.post(f"/api/v1/projects/{proj_id}/scan")
            assert scan_resp.status_code == 200
            rescan_resp = await client.post(f"/api/v1/projects/{proj_id}/scan")
            assert rescan_resp.json()["summary"]["unchanged_files"] == 1

            # 4. List project files
            files_resp = await client.get(f"/api/v1/projects/{proj_id}/files")
            assert files_resp.status_code == 200
            files_data = files_resp.json()
            assert files_data["total"] == 1
            assert files_data["files"][0]["relative_path"] == "index.ts"

            # 5. Delete project
            del_resp = await client.delete(f"/api/v1/projects/{proj_id}")
            assert del_resp.status_code == 204

            # 6. Verify 404 after deletion
            get_after_del = await client.get(f"/api/v1/projects/{proj_id}")
            assert get_after_del.status_code == 404
