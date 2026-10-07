"""
RepoMind AI — Phase 4 Code Parsing & Symbol Extraction Tests

Tests:
1. Python AST parser: functions, classes, methods, docstrings, signatures, imports
2. Python syntax error fallback parsing
3. TypeScript / JavaScript parser: functions, arrow functions, classes, interfaces, types, enums
4. Generic multi-language parser: Go, Rust, Java, SQL
5. SymbolExtractor service: database persistence, parent-child symbol linking
6. Symbols API: POST /parse, GET /symbols, filtering by name and kind, GET /symbols/{id}
"""
from pathlib import Path
import pytest
from httpx import ASGITransport, AsyncClient

from app.ingestion.parsers import (
    PythonCodeParser,
    TypeScriptJavaScriptParser,
    GenericMultiLanguageParser,
    parse_file_content,
)
from app.ingestion.service import IngestionService
from app.ingestion.symbol_extractor import SymbolExtractor
from app.main import app


class TestPythonASTParser:
    """Verifies Python AST parsing fidelity."""

    def setup_method(self):
        self.parser = PythonCodeParser()

    def test_parse_functions_and_classes(self):
        code = '''
"""Module docstring."""
import os
from typing import Optional

def standalone_func(x: int, y: str = "default") -> bool:
    """Check value."""
    return True

class Calculator:
    """Performs calculations."""

    def add(self, a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    async def async_fetch(self, url: str) -> None:
        pass
'''
        result = self.parser.parse(code, file_path="test_calc.py")
        assert result.status == "parsed"

        symbols_by_name = {s.name: s for s in result.symbols}
        assert "standalone_func" in symbols_by_name
        assert "Calculator" in symbols_by_name
        assert "add" in symbols_by_name
        assert "async_fetch" in symbols_by_name

        # Verify standalone function signature and docstring
        fn = symbols_by_name["standalone_func"]
        assert fn.kind == "function"
        assert "x: int" in fn.signature
        assert fn.docstring == "Check value."
        assert fn.parent_name is None

        # Verify class
        cls = symbols_by_name["Calculator"]
        assert cls.kind == "class"
        assert cls.docstring == "Performs calculations."

        # Verify method with parent_name
        method = symbols_by_name["add"]
        assert method.kind == "method"
        assert method.parent_name == "Calculator"
        assert method.docstring == "Add two numbers."
        assert "self" in method.signature

        # Verify async method
        async_method = symbols_by_name["async_fetch"]
        assert async_method.kind == "method"
        assert async_method.parent_name == "Calculator"
        assert "async def" in async_method.signature

        # Verify imports
        deps = {d.module for d in result.dependencies}
        assert "os" in deps
        assert "typing" in deps

    def test_python_syntax_error_fallback(self):
        malformed_code = """
def broken_syntax(a, b:
    print('missing paren')

class MyIncompleteClass:
    def inner_method(self):
"""
        result = self.parser.parse(malformed_code, file_path="broken.py")
        assert result.status == "partial"
        names = {s.name for s in result.symbols}
        assert "broken_syntax" in names or "MyIncompleteClass" in names


class TestTypeScriptJavaScriptParser:
    """Verifies TS and JS parsing."""

    def setup_method(self):
        self.parser = TypeScriptJavaScriptParser()

    def test_parse_typescript_constructs(self):
        code = """
import React, { useState } from 'react';
import { fetchHealth } from '@/services/api';

/**
 * User account profile.
 */
export interface UserProfile {
  id: string;
  name: string;
}

export type StatusType = 'active' | 'inactive';

export enum UserRole {
  Admin = 'admin',
  User = 'user',
}

export class AccountService {
  public async getAccount(id: string): Promise<UserProfile> {
    return { id, name: 'test' };
  }
}

export function formatName(first: string, last: string): string {
  return `${first} ${last}`;
}

export const HeaderComponent = () => {
  return <div>Header</div>;
};
"""
        result = self.parser.parse(code, file_path="account.ts")
        assert result.status == "parsed"

        symbols_by_name = {s.name: s for s in result.symbols}
        assert "UserProfile" in symbols_by_name
        assert symbols_by_name["UserProfile"].kind == "interface"
        assert "User account profile" in (symbols_by_name["UserProfile"].docstring or "")

        assert "StatusType" in symbols_by_name
        assert symbols_by_name["StatusType"].kind == "type"

        assert "UserRole" in symbols_by_name
        assert symbols_by_name["UserRole"].kind == "enum"

        assert "AccountService" in symbols_by_name
        assert symbols_by_name["AccountService"].kind == "class"

        assert "getAccount" in symbols_by_name
        assert symbols_by_name["getAccount"].kind == "method"
        assert symbols_by_name["getAccount"].parent_name == "AccountService"

        assert "formatName" in symbols_by_name
        assert symbols_by_name["formatName"].kind == "function"

        assert "HeaderComponent" in symbols_by_name
        assert symbols_by_name["HeaderComponent"].kind == "function"

        # Verify dependencies
        mods = {d.module for d in result.dependencies}
        assert "react" in mods
        assert "@/services/api" in mods


class TestGenericMultiLanguageParser:
    """Verifies parsing of other languages (Go, Rust, SQL)."""

    def setup_method(self):
        self.parser = GenericMultiLanguageParser()

    def test_parse_go_code(self):
        go_code = """
package main

type ServerConfig struct {
    Port int
}

func StartServer(cfg ServerConfig) error {
    return nil
}
"""
        res = self.parser.parse(go_code, file_path="main.go")
        names = {s.name for s in res.symbols}
        assert "ServerConfig" in names
        assert "StartServer" in names

    def test_parse_rust_code(self):
        rust_code = """
pub struct Pipeline {
    workers: usize,
}

pub async fn run_pipeline(p: Pipeline) {
}
"""
        res = self.parser.parse(rust_code, file_path="lib.rs")
        names = {s.name for s in res.symbols}
        assert "Pipeline" in names
        assert "run_pipeline" in names


class TestSymbolExtractorAndAPI:
    """Verifies database persistence, hierarchical linking, and API endpoints."""

    @pytest.mark.asyncio
    async def test_symbol_extraction_lifecycle_and_api(self, tmp_path: Path, test_db_session):
        repo_dir = tmp_path / "symbol_repo"
        repo_dir.mkdir()

        # Create Python file with class and methods
        py_file = repo_dir / "models.py"
        py_file.write_text(
            '''
class UserModel:
    """User database model."""
    def get_id(self) -> int:
        return 1

    def get_email(self) -> str:
        return "user@test.com"

def verify_user(user: UserModel) -> bool:
    """Verify validity."""
    return True
''',
            encoding="utf-8",
        )

        # 1. Ingest repository
        ingestion_service = IngestionService(test_db_session)
        project, _ = await ingestion_service.import_repository(str(repo_dir), name="Symbol Test")

        # 2. Extract symbols
        extractor = SymbolExtractor(test_db_session)
        stats = await extractor.extract_symbols_for_project(project.id)

        assert stats.files_processed == 1
        assert stats.total_symbols >= 4

        # 3. Test API via HTTP
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Re-parse via API
            parse_resp = await client.post(f"/api/v1/projects/{project.id}/parse")
            assert parse_resp.status_code == 200
            assert parse_resp.json()["status"] == "completed"

            # List symbols
            list_resp = await client.get(f"/api/v1/projects/{project.id}/symbols")
            assert list_resp.status_code == 200
            data = list_resp.json()
            assert data["total"] >= 4
            symbols = data["symbols"]
            sym_map = {s["name"]: s for s in symbols}

            assert "UserModel" in sym_map
            assert "get_id" in sym_map
            assert "get_email" in sym_map
            assert "verify_user" in sym_map

            # Check hierarchical linking: methods must have parent_symbol_id == UserModel's id
            user_model_id = sym_map["UserModel"]["id"]
            assert sym_map["get_id"]["parent_symbol_id"] == user_model_id
            assert sym_map["get_email"]["parent_symbol_id"] == user_model_id
            assert sym_map["verify_user"]["parent_symbol_id"] is None

            # Filter by kind=class
            class_filter_resp = await client.get(
                f"/api/v1/projects/{project.id}/symbols?kind=class"
            )
            assert class_filter_resp.status_code == 200
            class_data = class_filter_resp.json()
            assert len(class_data["symbols"]) == 1
            assert class_data["symbols"][0]["name"] == "UserModel"

            # Filter by partial name
            name_filter_resp = await client.get(
                f"/api/v1/projects/{project.id}/symbols?name=verify"
            )
            assert name_filter_resp.status_code == 200
            name_data = name_filter_resp.json()
            assert len(name_data["symbols"]) == 1
            assert name_data["symbols"][0]["name"] == "verify_user"

            # Get single symbol by ID
            single_resp = await client.get(
                f"/api/v1/projects/{project.id}/symbols/{user_model_id}"
            )
            assert single_resp.status_code == 200
            assert single_resp.json()["name"] == "UserModel"
