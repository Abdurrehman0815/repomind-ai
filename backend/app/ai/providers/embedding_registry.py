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

    The provider is selected based on the EMBEDDING_PROVIDER environment variable.

    Supported values:
        - 'local'  → LocalEmbeddingProvider (available from Phase 6)
        - 'bedrock' → BedrockEmbeddingProvider (available from Phase 32+)

    The rest of the application must call this function, never instantiate
    providers directly.
    """
    settings = get_settings()

    if settings.embedding_provider == "local":
        from app.ai.providers.local_embedding import LocalEmbeddingProvider
        return LocalEmbeddingProvider(
            model_name=settings.embedding_model,
            dimensions=settings.embedding_dimensions
        )
    elif settings.embedding_provider == "bedrock":
        # Bedrock embedding implementation is added in Phase 32.
        # Do not implement or import before all local phases pass.
        raise NotImplementedError(
            "Amazon Bedrock embedding provider is not yet implemented. "
            "Set EMBEDDING_PROVIDER=local for local operation."
        )
    else:
        raise ValueError(
            f"Unknown embedding provider: '{settings.embedding_provider}'. "
            f"Supported values: 'local' (and 'bedrock' in Phase 32+)."
        )