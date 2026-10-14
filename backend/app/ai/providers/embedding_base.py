"""
RepoMind AI — Embedding Provider Abstract Base

All embedding interactions go through this interface.
Application code never calls embedding models directly.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from pydantic import BaseModel


class EmbeddingOptions(BaseModel):
    """Options for embedding generation."""
    batch_size: int = 32
    normalize: bool = True


class EmbeddingResponse(BaseModel):
    """Response from an embedding provider."""
    embeddings: List[List[float]]
    model: str
    provider: str
    dimensions: int
    input_tokens: int | None = None
    latency_ms: float | None = None
    # Cost is 0.0 for local providers; real cost for cloud providers
    estimated_cost_usd: float = 0.0


class EmbeddingProvider(ABC):
    """
    Abstract base class for all embedding providers.

    Implementations:
        - LocalEmbeddingProvider  (Phase 6)
        - BedrockEmbeddingProvider (Phase 32+)

    The rest of the application must only use this interface.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider identifier string."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the current model name."""
        ...

    @property
    @abstractmethod
    def embedding_dimensions(self) -> int:
        """Return the embedding vector dimensions."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the provider is reachable and the model is available.
        Returns True if healthy, False otherwise.
        """
        ...

    @abstractmethod
    async def embed(
        self,
        texts: List[str],
        options: EmbeddingOptions | None = None,
    ) -> EmbeddingResponse:
        """
        Generate embeddings for the given texts.

        Args:
            texts: List of text strings to embed
            options: Embedding options (batch_size, normalize, etc.)

        Returns:
            EmbeddingResponse with embeddings and metadata
        """
        ...


class EmbeddingProviderError(Exception):
    """Base exception for all embedding provider errors."""
    pass


class EmbeddingProviderUnavailableError(EmbeddingProviderError):
    """Provider is not reachable."""
    pass


class EmbeddingProviderInvalidInputError(EmbeddingProviderError):
    """Provider received invalid input."""
    pass