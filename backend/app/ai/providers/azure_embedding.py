"""
RepoMind AI — Azure AI Foundry Embedding Provider

Embeds text with an Azure OpenAI-compatible embeddings deployment
(e.g. text-embedding-3-small). Batches are sent concurrently, which is what
makes indexing fast compared with CPU-only local embedding.
"""
from __future__ import annotations

import asyncio
import hashlib

import httpx
import structlog

from app.ai.providers.embedding_base import (
    EmbeddingOptions,
    EmbeddingProvider,
    EmbeddingProviderError,
    EmbeddingProviderUnavailableError,
    EmbeddingResponse,
)
from app.core.config import get_settings

logger = structlog.get_logger(__name__)

_BATCH_SIZE = 64
_CONCURRENCY = 6
_MAX_RETRIES = 5


class AzureEmbeddingProvider(EmbeddingProvider):
    """Embedding provider for an Azure AI Foundry embeddings deployment."""

    def __init__(self, endpoint: str, api_key: str, model_name: str, dimensions: int = 768) -> None:
        if not endpoint or not api_key or not model_name:
            raise EmbeddingProviderError(
                "Azure embeddings need EMBEDDING_MODEL plus an endpoint and key "
                "(EMBEDDING_ENDPOINT/EMBEDDING_API_KEY, or the LLM_* values)."
            )
        self._endpoint = endpoint.rstrip("/")
        self._api_key = api_key
        self._model_name = model_name
        self._dimensions = dimensions
        self._timeout = get_settings().llm_timeout
        self._semaphore = asyncio.Semaphore(_CONCURRENCY)
        # Identical text always yields the same vector, so never pay for it twice.
        self._cache: dict[str, list[float]] = {}
        self._cache_limit = 20000
        self._paths = ["/openai/v1/embeddings", "/embeddings"]

    @property
    def provider_name(self) -> str:
        return "azure_foundry"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def embedding_dimensions(self) -> int:
        return self._dimensions

    async def _embed_batch(self, client: httpx.AsyncClient, texts: list[str]) -> list[list[float]]:
        payload = {"model": self._model_name, "input": texts, "dimensions": self._dimensions}
        # Foundry accepts the key as either header depending on endpoint type.
        headers = {
            "api-key": self._api_key,
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        async with self._semaphore:
            for attempt in range(_MAX_RETRIES):
                resp = None
                # Foundry endpoints expose embeddings at /openai/v1/embeddings or /embeddings.
                try:
                    for path in self._paths:
                        resp = await client.post(f"{self._endpoint}{path}", headers=headers, json=payload)
                        if resp.status_code != 404:
                            self._paths = [path]  # remember the route that exists
                            break
                except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadError):
                    if attempt == _MAX_RETRIES - 1:
                        raise
                    logger.warning("azure_embedding_retry", reason="connection_dropped", attempt=attempt + 1)
                    await asyncio.sleep(1 + attempt)
                    continue
                if resp.status_code in (429, 500, 502, 503):
                    # Rate limited: honour Retry-After, else back off exponentially.
                    wait = float(resp.headers.get("retry-after", 2 ** attempt))
                    logger.warning("azure_embedding_retry", status=resp.status_code, wait_s=wait)
                    await asyncio.sleep(min(wait, 30))
                    continue
                if resp.status_code != 200:
                    raise EmbeddingProviderUnavailableError(
                        f"Azure embeddings returned {resp.status_code}: {resp.text[:300]}"
                    )
                items = sorted(resp.json().get("data", []), key=lambda item: item.get("index", 0))
                vectors = [item["embedding"] for item in items]
                if len(vectors) != len(texts) or any(len(v) != self._dimensions for v in vectors):
                    raise EmbeddingProviderError(
                        f"Unexpected embedding response (count/dimensions) from deployment '{self._model_name}'."
                    )
                return vectors
        raise EmbeddingProviderUnavailableError("Azure embeddings kept returning rate-limit/server errors.")

    async def embed(self, texts: list[str], options: EmbeddingOptions | None = None) -> EmbeddingResponse:
        if not isinstance(texts, list) or not all(isinstance(item, str) for item in texts):
            raise EmbeddingProviderError("texts must be a list of strings")
        non_empty = [item.strip() for item in texts if item.strip()]
        if not non_empty:
            return EmbeddingResponse(embeddings=[], model=self._model_name, provider=self.provider_name, dimensions=self._dimensions)

        keys = [hashlib.sha1(item.encode("utf-8")).hexdigest() for item in non_empty]
        missing: dict[str, str] = {}
        for key, item in zip(keys, non_empty):
            if key not in self._cache:
                missing.setdefault(key, item)

        fresh: dict[str, list[float]] = {}
        if missing:
            missing_keys = list(missing)
            batches = [missing_keys[i:i + _BATCH_SIZE] for i in range(0, len(missing_keys), _BATCH_SIZE)]
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    results = await asyncio.gather(
                        *(self._embed_batch(client, [missing[k] for k in batch]) for batch in batches)
                    )
            except httpx.HTTPError as exc:
                raise EmbeddingProviderUnavailableError(f"Failed to reach Azure embeddings: {exc}") from exc
            for batch, vectors in zip(batches, results):
                fresh.update(zip(batch, vectors))

        embeddings = [fresh[key] if key in fresh else self._cache[key] for key in keys]
        if len(self._cache) + len(fresh) > self._cache_limit:
            self._cache.clear()
        self._cache.update(fresh)
        return EmbeddingResponse(embeddings=embeddings, model=self._model_name, provider=self.provider_name, dimensions=self._dimensions)

    async def health_check(self) -> bool:
        try:
            result = await self.embed(["RepoMind embedding health check"])
            return len(result.embeddings) == 1
        except Exception as exc:
            logger.warning("azure_embedding_health_check_failed", error=str(exc))
            return False
