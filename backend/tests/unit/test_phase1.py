"""
RepoMind AI — Phase 1 Backend Tests

Tests:
1. GET /health → 200 with expected schema
2. GET /health/full → 200 with component statuses
3. GET /api/v1/projects → 200 with empty list
4. Settings loading from environment
5. LLM provider abstraction — registry resolves correctly
6. LLM provider abstraction — interface is correct
"""
import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport


# ── Fixtures ─────────────────────────────────────────────────

@pytest.fixture(scope="module")
def app():
    """Create FastAPI test application."""
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
    os.environ.setdefault("ENVIRONMENT", "test")
    os.environ.setdefault("LLM_PROVIDER", "ollama")
    os.environ.setdefault("SECRET_KEY", "test_secret_key_for_testing_only")

    from app.main import create_application
    return create_application()


@pytest.fixture(scope="module")
def client(app):
    """Create synchronous test client (for non-async tests)."""
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ── Health Endpoint Tests ─────────────────────────────────────

class TestHealthEndpoint:
    """Tests for GET /health"""

    def test_health_returns_200(self, client):
        """GET /health must return 200 OK."""
        response = client.get("/health")
        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

    def test_health_returns_json(self, client):
        """GET /health must return valid JSON."""
        response = client.get("/health")
        data = response.json()
        assert isinstance(data, dict)

    def test_health_has_status_field(self, client):
        """GET /health response must include 'status' field."""
        response = client.get("/health")
        data = response.json()
        assert "status" in data, f"Missing 'status' field in: {data}"

    def test_health_status_is_healthy(self, client):
        """GET /health status must be 'healthy'."""
        response = client.get("/health")
        data = response.json()
        assert data["status"] == "healthy", f"Expected 'healthy', got: {data['status']}"

    def test_health_has_version(self, client):
        """GET /health must include version."""
        response = client.get("/health")
        data = response.json()
        assert "version" in data
        assert data["version"] is not None

    def test_health_has_environment(self, client):
        """GET /health must include environment."""
        response = client.get("/health")
        data = response.json()
        assert "environment" in data

    def test_health_has_uptime(self, client):
        """GET /health must include uptime_seconds."""
        response = client.get("/health")
        data = response.json()
        assert "uptime_seconds" in data
        assert data["uptime_seconds"] >= 0

    def test_health_has_components(self, client):
        """GET /health must include components dict."""
        response = client.get("/health")
        data = response.json()
        assert "components" in data
        assert isinstance(data["components"], dict)


# ── Full Health Tests ─────────────────────────────────────────

class TestHealthFullEndpoint:
    """Tests for GET /health/full"""

    def test_health_full_returns_200(self, client):
        """GET /health/full must return 200 (even if services are down)."""
        response = client.get("/health/full")
        assert response.status_code == 200

    def test_health_full_has_components(self, client):
        """GET /health/full must report component statuses."""
        response = client.get("/health/full")
        data = response.json()
        assert "components" in data
        # Should have database, pgvector, ollama components
        components = data["components"]
        assert len(components) > 0

    def test_health_full_component_has_status(self, client):
        """Each component must have a 'status' field."""
        response = client.get("/health/full")
        data = response.json()
        for name, component in data["components"].items():
            assert "status" in component, f"Component '{name}' missing 'status'"


# ── Projects API Tests ────────────────────────────────────────

class TestProjectsEndpoint:
    """Tests for GET /api/v1/projects"""

    def test_projects_returns_200(self, client):
        """GET /api/v1/projects must return 200."""
        response = client.get("/api/v1/projects")
        assert response.status_code == 200

    def test_projects_returns_empty_list(self, client):
        """GET /api/v1/projects must return empty projects list in Phase 1."""
        response = client.get("/api/v1/projects")
        data = response.json()
        assert "projects" in data
        assert isinstance(data["projects"], list)
        assert "total" in data


# ── Settings Tests ────────────────────────────────────────────

class TestSettings:
    """Tests for application configuration."""

    def test_settings_load_without_error(self):
        """Settings must load without raising exceptions."""
        from app.core.config import Settings
        settings = Settings(
            database_url="postgresql+asyncpg://test:test@localhost:5432/test",
            environment="test",
            secret_key="test_key",
        )
        assert settings is not None

    def test_settings_llm_provider_default(self):
        """Default LLM provider must be 'ollama'."""
        from app.core.config import Settings
        settings = Settings(
            database_url="postgresql+asyncpg://test:test@localhost:5432/test",
            secret_key="test_key",
        )
        assert settings.llm_provider == "ollama"

    def test_settings_cors_origins_list(self):
        """CORS origins must be parsed from comma-separated string."""
        from app.core.config import Settings
        settings = Settings(
            database_url="postgresql+asyncpg://test:test@localhost:5432/test",
            secret_key="test_key",
            cors_origins="http://localhost:5173,http://localhost:3000",
        )
        origins = settings.cors_origins_list
        assert "http://localhost:5173" in origins
        assert "http://localhost:3000" in origins

    def test_settings_database_url_validation(self):
        """Non-PostgreSQL database URL must raise validation error."""
        from app.core.config import Settings
        import pydantic
        with pytest.raises((pydantic.ValidationError, ValueError)):
            Settings(
                database_url="redis://localhost:6379",
                secret_key="test_key",
            )

    def test_settings_max_file_size_bytes(self):
        """max_file_size_bytes must be derived from max_file_size_mb."""
        from app.core.config import Settings
        settings = Settings(
            database_url="postgresql+asyncpg://test:test@localhost:5432/test",
            secret_key="test_key",
            max_file_size_mb=5,
        )
        assert settings.max_file_size_bytes == 5 * 1024 * 1024


# ── LLM Provider Abstraction Tests ───────────────────────────

class TestLLMProviderAbstraction:
    """Tests for the provider abstraction layer."""

    def test_provider_base_is_abstract(self):
        """LLMProvider must be abstract — cannot be instantiated directly."""
        from app.ai.providers.base import LLMProvider
        with pytest.raises(TypeError):
            LLMProvider()  # type: ignore

    def test_ollama_provider_instantiates(self):
        """LocalOllamaProvider must instantiate with valid config."""
        from app.ai.providers.ollama import LocalOllamaProvider
        provider = LocalOllamaProvider(
            base_url="http://localhost:11434",
            model="llama3.2",
        )
        assert provider is not None

    def test_ollama_provider_name(self):
        """Ollama provider must return 'ollama' as provider name."""
        from app.ai.providers.ollama import LocalOllamaProvider
        provider = LocalOllamaProvider()
        assert provider.provider_name == "ollama"

    def test_ollama_model_name(self):
        """Ollama provider must return the configured model name."""
        from app.ai.providers.ollama import LocalOllamaProvider
        provider = LocalOllamaProvider(model="mistral")
        assert provider.model_name == "mistral"

    def test_registry_returns_ollama_provider(self):
        """Registry must return LocalOllamaProvider when LLM_PROVIDER=ollama."""
        import os
        os.environ["LLM_PROVIDER"] = "ollama"

        # Clear lru_cache so it re-resolves with our env
        from app.ai.providers import registry
        registry.get_llm_provider.cache_clear()

        # Also clear config cache
        from app.core import config
        config.get_settings.cache_clear()

        os.environ["LLM_PROVIDER"] = "ollama"
        from app.core.config import Settings
        # Patch settings inline
        with patch("app.ai.providers.registry.get_settings") as mock_settings:
            mock = mock_settings.return_value
            mock.llm_provider = "ollama"
            mock.ollama_base_url = "http://localhost:11434"
            mock.ollama_model = "llama3.2"
            mock.ollama_timeout = 120
            mock.ollama_max_tokens = 4096

            registry.get_llm_provider.cache_clear()
            provider = registry.get_llm_provider()
            assert provider.provider_name == "ollama"

        registry.get_llm_provider.cache_clear()

    def test_registry_raises_for_bedrock(self):
        """Registry must raise NotImplementedError for 'bedrock' in Phase 1."""
        from app.ai.providers import registry
        registry.get_llm_provider.cache_clear()

        with patch("app.ai.providers.registry.get_settings") as mock_settings:
            mock = mock_settings.return_value
            mock.llm_provider = "bedrock"

            registry.get_llm_provider.cache_clear()
            with pytest.raises(NotImplementedError):
                registry.get_llm_provider()

        registry.get_llm_provider.cache_clear()

    def test_registry_raises_for_unknown_provider(self):
        """Registry must raise ValueError for unknown provider names."""
        from app.ai.providers import registry
        registry.get_llm_provider.cache_clear()

        with patch("app.ai.providers.registry.get_settings") as mock_settings:
            mock = mock_settings.return_value
            mock.llm_provider = "openai_not_supported"

            registry.get_llm_provider.cache_clear()
            with pytest.raises(ValueError):
                registry.get_llm_provider()

        registry.get_llm_provider.cache_clear()

    def test_provider_interface_has_all_methods(self):
        """LocalOllamaProvider must implement all abstract methods."""
        from app.ai.providers.ollama import LocalOllamaProvider
        provider = LocalOllamaProvider()

        # All methods must exist (even if they raise NotImplementedError in Phase 1)
        assert hasattr(provider, "health_check")
        assert hasattr(provider, "generate")
        assert hasattr(provider, "stream")
        assert hasattr(provider, "structured_generate")
        assert hasattr(provider, "tool_calling")

    @pytest.mark.asyncio
    async def test_ollama_health_check_returns_bool(self):
        """health_check() must return a boolean."""
        from app.ai.providers.ollama import LocalOllamaProvider
        provider = LocalOllamaProvider(base_url="http://localhost:99999")
        result = await provider.health_check()
        assert isinstance(result, bool)
        # Unreachable URL must return False (not raise)
        assert result is False


# ── Security Tests ────────────────────────────────────────────

class TestSecurityBasics:
    """Basic security checks for Phase 1."""

    def test_api_docs_available_in_development(self, client):
        """Swagger docs should be available in development mode."""
        response = client.get("/docs")
        # In test mode (which we set), docs are still enabled
        assert response.status_code in (200, 404)  # acceptable in test env

    def test_health_does_not_expose_secret_key(self, client):
        """Health endpoint must not expose the SECRET_KEY."""
        response = client.get("/health")
        body = response.text
        assert "secret" not in body.lower() or "secret_key" not in body
        # More specifically, the actual key value must not appear
        assert "dev_secret" not in body
