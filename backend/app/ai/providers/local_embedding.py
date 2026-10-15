"""
RepoMind AI — Local Embedding Provider

Implements local embedding generation using sentence-transformers.
Supports configurable models and batch processing.
"""
from __future__ import annotations

import asyncio
import logging
from typing import List, Optional
import numpy as np

from app.ai.providers.embedding_base import EmbeddingProvider, EmbeddingOptions, EmbeddingResponse, EmbeddingProviderError
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class LocalEmbeddingProvider(EmbeddingProvider):
    """
    Local embedding provider using sentence-transformers.

    Supports:
    - Configurable embedding models
    - Batch processing
    - Automatic normalization
    - CPU/GPU detection
    - Retry handling
    """

    def __init__(
        self,
        model_name: str = "nomic-embed-text-v1.5",
        dimensions: int = 768,
        device: Optional[str] = None,
        cache_folder: Optional[str] = None
    ):
        """
        Initialize the local embedding provider.

        Args:
            model_name: Name of the sentence-transformers model to use
            dimensions: Expected embedding dimensions
            device: Device to use ('cpu', 'cuda', etc.). Auto-detected if None
            cache_folder: Folder to cache models. Uses default if None
        """
        self._model_name = model_name
        self._dimensions = dimensions
        self.settings = get_settings()
        self._model = None
        self._device = device
        self._cache_folder = cache_folder
        self._model_ready = False

        # Initialize model asynchronously to avoid blocking startup
        self._init_task: Optional[asyncio.Task] = None

    @property
    def provider_name(self) -> str:
        return "local"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def embedding_dimensions(self) -> int:
        return self._dimensions

    async def _ensure_model_loaded(self) -> None:
        """Ensure the embedding model is loaded."""
        if self._model_ready:
            return

        if self._init_task is not None:
            # Wait for existing initialization task
            await self._init_task
            return

        # Start model initialization
        self._init_task = asyncio.create_task(self._load_model())
        await self._init_task

    async def _load_model(self) -> None:
        """Load the sentence-transformers model."""
        try:
            logger.info("Loading local embedding model", model=self._model_name)

            # Import sentence-transformers here to avoid blocking if not installed
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as e:
                raise EmbeddingProviderError(
                    "sentence-transformers not installed. "
                    "Install with: pip install sentence-transformers"
                ) from e

            # Determine device
            if self._device is None:
                try:
                    import torch
                    self._device = "cuda" if torch.cuda.is_available() else "cpu"
                except ImportError:
                    self._device = "cpu"

            logger.info("Using device for embeddings", device=self._device)

            # Load model
            self._model = SentenceTransformer(
                self._model_name,
                device=self._device,
                cache_folder=self._cache_folder
            )

            # Verify dimensions match expectation
            actual_dimensions = self._model.get_sentence_embedding_dimension()
            if actual_dimensions != self._dimensions:
                logger.warning(
                    "Embedding dimensions mismatch",
                    expected=self._dimensions,
                    actual=actual_dimensions,
                    model=self._model_name
                )
                # Update to actual dimensions
                self._dimensions = actual_dimensions

            self._model_ready = True
            logger.info(f"Local embedding model loaded successfully: model={self._model_name}, dimensions={self._dimensions}, device={self._device}")

        except Exception as e:
            logger.error(f"Failed to load embedding model: {str(e)} (model={self._model_name})")
            self._model_ready = False
            raise EmbeddingProviderError(f"Failed to load embedding model: {e}") from e
        finally:
            # Clean up the task reference
            self._init_task = None

    async def health_check(self) -> bool:
        """Check if the embedding provider is healthy."""
        try:
            await self._ensure_model_loaded()
            return self._model is not None and self._model_ready
        except Exception as e:
            logger.warning("Embedding provider health check failed", error=str(e))
            return False

    async def embed(
        self,
        texts: List[str],
        options: EmbeddingOptions | None = None,
    ) -> EmbeddingResponse:
        """
        Generate embeddings for the given texts.

        Args:
            texts: List of text strings to embed
            options: Embedding options

        Returns:
            EmbeddingResponse with embeddings and metadata
        """
        if not texts:
            return EmbeddingResponse(
                embeddings=[],
                model=self._model_name,
                provider=self.provider_name,
                dimensions=self._dimensions
            )

        options = options or EmbeddingOptions()

        # Ensure model is loaded
        await self._ensure_model_loaded()

        if not self._model_ready or self._model is None:
            raise EmbeddingProviderUnavailableError("Embedding model not available")

        # Validate input
        if not isinstance(texts, list) or not all(isinstance(t, str) for t in texts):
            raise EmbeddingProviderInvalidInputError("texts must be a list of strings")

        # Filter out empty texts
        non_empty_texts = [t.strip() for t in texts if t.strip()]
        if not non_empty_texts:
            return EmbeddingResponse(
                embeddings=[],
                model=self._model_name,
                provider=self.provider_name,
                dimensions=self._dimensions
            )

        try:
            import time
            start_time = time.time()

            # Process in batches
            all_embeddings = []
            batch_size = options.batch_size or self.settings.embedding_batch_size

            for i in range(0, len(non_empty_texts), batch_size):
                batch = non_empty_texts[i:i + batch_size]

                # Generate embeddings for batch
                batch_embeddings = self._model.encode(
                    batch,
                    normalize_embeddings=options.normalize,
                    show_progress_bar=False
                )

                # Convert to list of lists
                if hasattr(batch_embeddings, 'tolist'):
                    batch_embeddings = batch_embeddings.tolist()
                elif isinstance(batch_embeddings, np.ndarray):
                    batch_embeddings = batch_embeddings.tolist()

                all_embeddings.extend(batch_embeddings)

                # Allow other tasks to run between batches
                if i + batch_size < len(non_empty_texts):
                    await asyncio.sleep(0)

            latency_ms = (time.time() - start_time) * 1000

            logger.debug(f"Generated embeddings: count={len(all_embeddings)}, batch_size={batch_size}, latency_ms={round(latency_ms, 2)}")

            return EmbeddingResponse(
                embeddings=all_embeddings,
                model=self._model_name,
                provider=self.provider_name,
                dimensions=self._dimensions,
                latency_ms=round(latency_ms, 2)
            )

        except Exception as e:
            logger.error(f"Failed to generate embeddings: {str(e)} (count={len(texts)})")
            raise EmbeddingProviderError(f"Failed to generate embeddings: {e}") from e


# Alias for backward compatibility
LocalEmbeddingProviderImpl = LocalEmbeddingProvider