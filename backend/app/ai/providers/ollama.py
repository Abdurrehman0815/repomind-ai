"""
RepoMind AI — Ollama LLM Provider (Stub for Phase 1)

Full implementation in Phase 9.
This stub satisfies the provider interface so the registry works and
tests can verify the abstraction is wired up correctly.
"""
import asyncio
import json
import time
from typing import Any, AsyncIterator, Type, TypeVar

import structlog

from app.ai.providers.base import (
    GenerateOptions,
    LLMProvider,
    LLMProviderUnavailableError,
    LLMResponse,
    LLMStructuredOutputError,
    LLMTimeoutError,
    StreamChunk,
    ToolCallResult,
    ToolDefinition,
)

logger = structlog.get_logger(__name__)
T = TypeVar("T")


class LocalOllamaProvider(LLMProvider):
    """
    Ollama local LLM provider.

    Phase 1: Minimal stub that validates the abstraction works.
    Phase 9: Full implementation with generate, stream, structured_generate, tool_calling.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.2",
        timeout: int = 120,
        max_tokens: int = 4096,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._max_tokens = max_tokens
        logger.info(
            "ollama_provider_initialized",
            base_url=self._base_url,
            model=self._model,
        )

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._model

    async def health_check(self) -> bool:
        """Check if Ollama server is reachable."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/api/version")
            return resp.status_code == 200
        except Exception as exc:
            logger.warning("ollama_health_check_failed", error=str(exc))
            return False

    async def generate(
        self,
        prompt: str,
        options: GenerateOptions | None = None,
    ) -> LLMResponse:
        """
        Generate a response from Ollama.
        Phase 9 will implement the full Ollama API call.
        """
        raise NotImplementedError(
            "LocalOllamaProvider.generate() will be implemented in Phase 9. "
            "The provider abstraction is verified — the registry and interfaces work."
        )

    async def stream(
        self,
        prompt: str,
        options: GenerateOptions | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream a response from Ollama.
        Phase 9 will implement the full streaming API call.
        """
        raise NotImplementedError(
            "LocalOllamaProvider.stream() will be implemented in Phase 9."
        )
        # Make type checker happy — this line is never reached
        yield StreamChunk(content="", is_final=True)  # type: ignore[misc]

    async def structured_generate(
        self,
        prompt: str,
        schema: Type[T],
        options: GenerateOptions | None = None,
    ) -> T:
        """
        Generate structured output.
        Phase 9 will implement this using Ollama's JSON mode.
        """
        raise NotImplementedError(
            "LocalOllamaProvider.structured_generate() will be implemented in Phase 9."
        )

    async def tool_calling(
        self,
        prompt: str,
        tools: list[ToolDefinition],
        options: GenerateOptions | None = None,
    ) -> ToolCallResult:
        """
        Tool calling via Ollama.
        Phase 9 will implement this using Ollama's tool_call format.
        """
        raise NotImplementedError(
            "LocalOllamaProvider.tool_calling() will be implemented in Phase 9."
        )
