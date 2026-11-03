"""
RepoMind AI — Embedding Provider Registry

Resolves the configured embedding provider at runtime.
"""
from __future__ import annotations

from functools import lru_cache

from app.ai.providers.embedding_base import EmbeddingProvider
from app.core.config import get_settings


@lru_cache(maxsize=1)
def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()

    if settings.embedding_provider == "ollama":
        from app.ai.providers.ollama_embedding import OllamaEmbeddingProvider
        return OllamaEmbeddingProvider(
            model_name=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )
    elif settings.embedding_provider == "local":
        from app.ai.providers.local_embedding import LocalEmbeddingProvider
        return LocalEmbeddingProvider(
            model_name=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )
    elif settings.embedding_provider == "azure_foundry":
        from app.ai.providers.azure_embedding import AzureEmbeddingProvider
        return AzureEmbeddingProvider(
            endpoint=settings.embedding_endpoint or settings.llm_endpoint,
            api_key=settings.embedding_api_key or settings.llm_api_key,
            model_name=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )
    elif settings.embedding_provider == "bedrock":
        # Bedrock embedding implementation is added in Phase 32.
        # Do not implement or import before all local phases pass.
        raise NotImplementedError(
            "Amazon Bedrock embedding provider is not yet implemented. "
            "Set EMBEDDING_PROVIDER=local or 'ollama' for local operation."
        )
    else:
        raise ValueError(
            f"Unknown embedding provider: '{settings.embedding_provider}'. "
            f"Supported values: 'local', 'ollama', 'azure_foundry'."
        )