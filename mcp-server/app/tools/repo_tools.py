"""
RepoMind AI — MCP Repository Tools

Provides codebase exploration and retrieval tools:
- repo_list_files: explore files in repository respecting ignore & security rules
- repo_read_file: read file contents safely with line range slicing
- repo_search: search indexed codebase using hybrid vector + keyword search
- repo_get_symbols: inspect extracted AST code symbols
- repo_get_dependencies: retrieve code dependencies and module import graph
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.ingestion.scanner import load_gitignore_spec, detect_language
from app.models.project import Project
from app.repositories.dependency_repository import DependencyRepository
from app.repositories.file_repository import FileRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.symbol_repository import SymbolRepository
from app.services.retrieval_service import RetrievalService
from ..security import SecurityError, is_sensitive_path, validate_repo_path

logger = structlog.get_logger(__name__)


async def resolve_project(project_id: str, session: Optional[AsyncSession] = None) -> Project:
    """
    Resolve a Project entity from either UUID, repository path, or directory fallback.
    """
    if not project_id or not project_id.strip():
        raise ValueError("project_id must not be empty")

    # 1. If project_id represents an existing local directory, return directly without DB
    try:
        p = Path(project_id).resolve()
        if p.exists() and p.is_dir():
            return Project(
                id=project_id,
                name=p.name,
                path=str(p),
                status="unindexed",
            )
    except Exception:
        pass

    async def _query(s: AsyncSession) -> Project:
        project_repo = ProjectRepository(s)
        proj = await project_repo.get_by_id(project_id)
        if proj:
            return proj
        proj = await project_repo.get_by_path(project_id)
        if proj:
            return proj
        raise ValueError(f"Project not found for identifier: '{project_id}'")

    if session is not None:
        return await _query(session)

    async with AsyncSessionLocal() as s:
        return await _query(s)


async def repo_list_files(
    project_id: str,
    directory: str = ".",
    recursive: bool = True,
    limit: int = 100,
    db_session: Optional[AsyncSession] = None,
) -> dict[str, Any]:
    """
    List files in repository respecting .gitignore, exclusions, and path security.
    """
    if limit <= 0:
        limit = 100
    limit = min(limit, 1000)

    project = await resolve_project(project_id, db_session)
    repo_root = Path(project.path).resolve()
    target_dir = validate_repo_path(repo_root, directory)

    if not target_dir.exists() or not target_dir.is_dir():
        raise FileNotFoundError(f"Target directory does not exist: {directory}")

    spec = load_gitignore_spec(repo_root)
    files_found: list[dict[str, Any]] = []

    if recursive:
        walk_iter = os.walk(target_dir, topdown=True, followlinks=False)
    else:
        # Single-level listing
        entries = os.listdir(target_dir)
        filenames = [e for e in entries if (target_dir / e).is_file()]
        dirnames = [e for e in entries if (target_dir / e).is_dir()]
        walk_iter = [(str(target_dir), dirnames, filenames)]

    for dirpath, dirnames, filenames in walk_iter:
        current = Path(dirpath)
        try:
            rel_dir = current.relative_to(repo_root).as_posix()
        except ValueError:
            continue

        # Prune ignored and sensitive directories
        pruned_dirs: list[str] = []
        for d in dirnames:
            cand = f"{rel_dir}/{d}" if rel_dir != "." else d
            if spec.match_file(cand) or spec.match_file(f"{cand}/") or is_sensitive_path(d):
                continue
            pruned_dirs.append(d)
        dirnames[:] = pruned_dirs

        for f in filenames:
            file_path = current / f
            if is_sensitive_path(file_path):
                continue

            try:
                rel_file = file_path.relative_to(repo_root).as_posix()
            except ValueError:
                continue

            if spec.match_file(rel_file):
                continue

            try:
                st = file_path.stat()
                size_bytes = st.st_size
            except OSError:
                size_bytes = 0

            lang = detect_language(file_path) or "unknown"

            files_found.append({
                "relative_path": rel_file,
                "language": lang,
                "size_bytes": size_bytes,
            })

            if len(files_found) >= limit:
                break

        if len(files_found) >= limit:
            break

    return {
        "project_id": project.id,
        "project_path": project.path,
        "directory": directory,
        "total_found": len(files_found),
        "limit": limit,
        "files": files_found,
    }


async def repo_read_file(
    project_id: str,
    file_path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    db_session: Optional[AsyncSession] = None,
) -> dict[str, Any]:
    """
    Safely read contents of a file within the repository, with optional line range.
    """
    if not file_path or not file_path.strip():
        raise ValueError("file_path must not be empty")

    if start_line is not None and start_line < 1:
        raise ValueError("start_line must be >= 1")
    if end_line is not None and end_line < 1:
        raise ValueError("end_line must be >= 1")
    if start_line is not None and end_line is not None and start_line > end_line:
        raise ValueError(f"start_line ({start_line}) cannot be greater than end_line ({end_line})")

    project = await resolve_project(project_id, db_session)
    repo_root = Path(project.path).resolve()
    target = validate_repo_path(repo_root, file_path)

    if not target.exists():
        raise FileNotFoundError(f"File not found: '{file_path}'")
    if not target.is_file():
        raise ValueError(f"Requested path is not a regular file: '{file_path}'")

    try:
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception as exc:
        raise IOError(f"Could not read file '{file_path}': {str(exc)}") from exc

    total_lines = len(lines)
    s_line = start_line if start_line is not None else 1
    e_line = end_line if end_line is not None else total_lines

    # Clamp range
    s_line = max(1, min(s_line, total_lines if total_lines > 0 else 1))
    e_line = max(s_line, min(e_line, total_lines))

    selected_lines = lines[s_line - 1 : e_line] if total_lines > 0 else []
    content = "".join(selected_lines)

    return {
        "project_id": project.id,
        "file_path": file_path,
        "start_line": s_line,
        "end_line": e_line,
        "total_lines": total_lines,
        "content": content,
    }



async def repo_search(
    project_id: str,
    query: str,
    limit: int = 10,
    file_id: Optional[str] = None,
    language: Optional[str] = None,
    db_session: Optional[AsyncSession] = None,
) -> dict[str, Any]:
    """
    Search indexed repository using hybrid vector and keyword search.
    """
    if not query or not query.strip():
        raise ValueError("query must not be empty")

    limit = max(1, min(limit, 50))

    async def _impl(session: AsyncSession) -> dict[str, Any]:
        project = await resolve_project(project_id, session)
        retrieval_service = RetrievalService(session)

        results = await retrieval_service.hybrid_search(
            query_text=query,
            project_id=project.id,
            file_id=file_id,
            language=language,
            limit=limit,
        )

        file_repo = FileRepository(session)
        items: list[dict[str, Any]] = []

        for chunk, score in results:
            file_doc = await file_repo.get_by_id(chunk.file_id)
            rel_path = file_doc.relative_path if file_doc else "unknown"

            items.append({
                "chunk_id": chunk.id,
                "file_id": chunk.file_id,
                "file_path": rel_path,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "score": round(score, 4),
                "content": chunk.content,
            })

        return {
            "project_id": project.id,
            "query": query,
            "total_found": len(items),
            "results": items,
        }

    if db_session is not None:
        return await _impl(db_session)
    async with AsyncSessionLocal() as session:
        return await _impl(session)


async def repo_get_symbols(
    project_id: str,
    file_path: Optional[str] = None,
    name: Optional[str] = None,
    kind: Optional[str] = None,
    limit: int = 50,
    db_session: Optional[AsyncSession] = None,
) -> dict[str, Any]:
    """
    Get extracted AST code symbols for a project or specific file/name/kind.
    """
    limit = max(1, min(limit, 200))

    async def _impl(session: AsyncSession) -> dict[str, Any]:
        project = await resolve_project(project_id, session)
        symbol_repo = SymbolRepository(session)
        file_repo = FileRepository(session)

        symbols = []
        if file_path:
            file_doc = await file_repo.get_by_relative_path(project.id, file_path)
            if file_doc:
                symbols = await symbol_repo.list_by_file(file_doc.id)
            else:
                symbols = []
        elif name:
            symbols = await symbol_repo.search_by_name(project.id, name)
        else:
            # Get symbols for the project across files
            files = await file_repo.list_by_project(project.id)
            for f in files:
                syms = await symbol_repo.list_by_file(f.id)
                symbols.extend(syms)
                if len(symbols) >= limit:
                    break

        # Filter by kind if specified
        if kind:
            symbols = [s for s in symbols if s.kind.lower() == kind.lower()]

        symbols = symbols[:limit]

        results = [
            {
                "symbol_id": s.id,
                "name": s.name,
                "kind": s.kind,
                "line_start": s.line_start,
                "line_end": s.line_end,
                "signature": s.signature,
                "docstring": s.docstring,
                "parent_symbol_id": s.parent_symbol_id,
            }
            for s in symbols
        ]

        return {
            "project_id": project.id,
            "total_symbols": len(results),
            "symbols": results,
        }

    if db_session is not None:
        return await _impl(db_session)
    async with AsyncSessionLocal() as session:
        return await _impl(session)


async def repo_get_dependencies(
    project_id: str,
    file_path: Optional[str] = None,
    limit: int = 50,
    db_session: Optional[AsyncSession] = None,
) -> dict[str, Any]:
    """
    Get dependencies and import edges for a project or specific file.
    """
    limit = max(1, min(limit, 200))

    async def _impl(session: AsyncSession) -> dict[str, Any]:
        project = await resolve_project(project_id, session)
        dep_repo = DependencyRepository(session)
        file_repo = FileRepository(session)

        if file_path:
            file_doc = await file_repo.get_by_relative_path(project.id, file_path)
            if file_doc:
                deps = await dep_repo.list_by_file(file_doc.id)
            else:
                deps = []
        else:
            deps = await dep_repo.list_by_project(project.id)

        deps = list(deps[:limit])

        results = []
        for d in deps:
            src_doc = await file_repo.get_by_id(d.source_file_id) if d.source_file_id else None
            tgt_doc = await file_repo.get_by_id(d.target_file_id) if d.target_file_id else None

            results.append({
                "dependency_id": d.id,
                "source_file": src_doc.relative_path if src_doc else None,
                "target_file": tgt_doc.relative_path if tgt_doc else None,
                "target_module": d.target_module,
                "symbol_name": d.symbol_name,
                "import_statement": d.import_statement,
                "line_number": d.line_number,
            })

        return {
            "project_id": project.id,
            "total_dependencies": len(results),
            "dependencies": results,
        }

    if db_session is not None:
        return await _impl(db_session)
    async with AsyncSessionLocal() as session:
        return await _impl(session)
