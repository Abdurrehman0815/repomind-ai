"""
RepoMind AI — Symbols & Code AST API

Provides endpoints for symbol parsing, symbol lookup, and AST search.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog

from app.db.session import get_db
from app.ingestion.symbol_extractor import SymbolExtractor
from app.models.code_symbol import CodeSymbol
from app.repositories.project_repository import ProjectRepository
from app.repositories.symbol_repository import SymbolRepository
from app.schemas.symbol import (
    CodeSymbolResponse,
    SymbolListResponse,
    SymbolParseResponse,
)

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.post(
    "/{project_id}/parse",
    response_model=SymbolParseResponse,
    status_code=status.HTTP_200_OK,
)
async def parse_project_symbols(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> SymbolParseResponse:
    """
    Trigger AST parsing and symbol extraction across all files in the project.
    """
    project_repo = ProjectRepository(db)
    proj = await project_repo.get_by_id(project_id)
    if not proj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found.",
        )

    extractor = SymbolExtractor(db)
    try:
        stats = await extractor.extract_symbols_for_project(project_id)
    except Exception as exc:
        logger.error("symbol_parsing_failed", project_id=project_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Symbol extraction failed: {exc}",
        )

    return SymbolParseResponse(
        project_id=project_id,
        status="completed",
        stats=stats.to_dict(),
    )


@router.get(
    "/{project_id}/symbols",
    response_model=SymbolListResponse,
)
async def list_symbols(
    project_id: str,
    name: str | None = Query(None, description="Filter symbols by partial name"),
    kind: str | None = Query(None, description="Filter by kind: function, class, method, interface"),
    file_id: str | None = Query(None, description="Filter symbols by source file ID"),
    db: AsyncSession = Depends(get_db),
) -> SymbolListResponse:
    """
    List and filter extracted code symbols for a project.
    """
    project_repo = ProjectRepository(db)
    proj = await project_repo.get_by_id(project_id)
    if not proj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found.",
        )

    query = select(CodeSymbol).where(CodeSymbol.project_id == project_id)

    if name:
        query = query.where(CodeSymbol.name.ilike(f"%{name}%"))
    if kind:
        query = query.where(CodeSymbol.kind == kind.lower())
    if file_id:
        query = query.where(CodeSymbol.file_id == file_id)

    query = query.order_by(CodeSymbol.name)

    result = await db.execute(query)
    symbols = result.scalars().all()

    return SymbolListResponse(
        symbols=[
            CodeSymbolResponse(
                id=s.id,
                project_id=s.project_id,
                file_id=s.file_id,
                name=s.name,
                kind=s.kind,
                line_start=s.line_start,
                line_end=s.line_end,
                signature=s.signature,
                docstring=s.docstring,
                parent_symbol_id=s.parent_symbol_id,
                created_at=s.created_at,
            )
            for s in symbols
        ],
        total=len(symbols),
    )


@router.get(
    "/{project_id}/symbols/{symbol_id}",
    response_model=CodeSymbolResponse,
)
async def get_symbol(
    project_id: str,
    symbol_id: str,
    db: AsyncSession = Depends(get_db),
) -> CodeSymbolResponse:
    """
    Retrieve single symbol details by ID.
    """
    symbol_repo = SymbolRepository(db)
    sym = await symbol_repo.get_by_id(symbol_id)
    if not sym or sym.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol with ID '{symbol_id}' not found.",
        )

    return CodeSymbolResponse(
        id=sym.id,
        project_id=sym.project_id,
        file_id=sym.file_id,
        name=sym.name,
        kind=sym.kind,
        line_start=sym.line_start,
        line_end=sym.line_end,
        signature=sym.signature,
        docstring=sym.docstring,
        parent_symbol_id=sym.parent_symbol_id,
        created_at=sym.created_at,
    )
