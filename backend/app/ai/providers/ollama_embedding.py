from __future__ import annotations

import asyncio
import json
import math
import urllib.request
from typing import List

from app.ai.providers.embedding_base import (
    EmbeddingProvider,
    EmbeddingOptions,
    EmbeddingResponse,
    EmbeddingProviderError,
)
from app.core.config import get_settings


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Generate embeddings through the Ollama HTTP API."""

    def __init__(
        self,
        model_name: str = "nomic-embed-text",
        dimensions: int = 768,
    ) -> None:
        self.settings = get_settings()
        self._model_name = model_name
        self._dimensions = dimensions
        self._base_url = self.settings.ollama_base_url.rstrip("/")
        self._timeout = self.settings.ollama_timeout

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def embedding_dimensions(self) -> int:
        return self._dimensions

    def _embed_batch(self, texts: List[str]) -> list[list[float]]:
        payload = json.dumps({
            "model": self._model_name,
            "input": texts,
        }).encode("utf-8")

        request = urllib.request.Request(
            f"{self._base_url}/api/embed",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request, timeout=self._timeout
            ) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise EmbeddingProviderError(
                f"Ollama embedding request failed: {exc}"
            ) from exc

        embeddings = data.get("embeddings")
        if not isinstance(embeddings, list):
            raise EmbeddingProviderError(
                "Ollama response did not contain an embeddings list"
            )

        vectors = []
        for vector in embeddings:
            if len(vector) != self._dimensions:
                raise EmbeddingProviderError(
                    f"Expected {self._dimensions} dimensions, "
                    f"received {len(vector)}"
                )
            vectors.append([float(value) for value in vector])

        if len(vectors) != len(texts):
            raise EmbeddingProviderError(
                f"Expected {len(texts)} embeddings, got {len(vectors)}"
            )

        return vectors

    async def embed(
        self,
        texts: List[str],
        options: EmbeddingOptions | None = None,
    ) -> EmbeddingResponse:
        if not isinstance(texts, list) or not all(
            isinstance(item, str) for item in texts
        ):
            raise EmbeddingProviderError(
                "texts must be a list of strings"
            )

        options = options or EmbeddingOptions()
        non_empty = [item.strip() for item in texts if item.strip()]

        if not non_empty:
            return EmbeddingResponse(
                embeddings=[],
                model=self._model_name,
                provider=self.provider_name,
                dimensions=self._dimensions,
            )

        batch_size = options.batch_size or self.settings.embedding_batch_size
        if batch_size < 1:
            raise EmbeddingProviderError("batch_size must be positive")

        all_embeddings = []

        for start in range(0, len(non_empty), batch_size):
            batch = non_empty[start:start + batch_size]
            vectors = await asyncio.to_thread(self._embed_batch, batch)

            if options.normalize:
                normalized_vectors = []
                for vector in vectors:
                    norm = math.sqrt(sum(value * value for value in vector))
                    normalized_vectors.append(
                        [value / norm for value in vector]
                        if norm > 0 else vector
                    )
                vectors = normalized_vectors

            all_embeddings.extend(vectors)

        return EmbeddingResponse(
            embeddings=all_embeddings,
            model=self._model_name,
            provider=self.provider_name,
            dimensions=self._dimensions,
        )

    async def health_check(self) -> bool:
        try:
            result = await self.embed(
                ["RepoMind embedding health check"],
                EmbeddingOptions(batch_size=1, normalize=True),
            )
            return (
                len(result.embeddings) == 1
                and len(result.embeddings[0]) == self._dimensions
            )
        except Exception:
            return False
