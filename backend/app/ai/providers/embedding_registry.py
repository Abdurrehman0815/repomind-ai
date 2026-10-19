"""
RepoMind AI — Embedding Provider Registry

Resolves the configured embedding provider at runtime.
"""

from functools import lru_cache

from app.ai.providers.embedding_base import EmbeddingProvider
from app.core.config import get_settings


@lru_cache(maxsize=1)
def get_embedding_provider() -> EmbeddingProvider:
    """
    Return the configured embedding provider instance.

    The provider is selected using the EMBEDDING_PROVIDER environment variable.

    Supported providers:
        - ollama: Uses Ollama's embedding API.
        - local: Uses Sentence Transformers.
        - bedrock: Reserved for a future implementation.

    Other parts of the application should call this function instead
    of instantiating providers directly.
    """
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

    elif settings.embedding_provider == "bedrock":
        raise NotImplementedError(
            "Amazon Bedrock embedding provider is not yet implemented. "
            "Set EMBEDDING_PROVIDER=ollama for local Ollama operation."
        )

    else:
        raise ValueError(
            f"Unknown embedding provider: '{settings.embedding_provider}'. "
            "Supported values: 'ollama', 'local', and 'bedrock' "
            "(bedrock is not implemented yet)."
        )