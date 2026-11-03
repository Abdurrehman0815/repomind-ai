"""
RepoMind AI — Azure AI Foundry LLM Provider

Calls a model deployed in Azure AI Foundry over HTTPS. Two wire formats are
supported because Foundry serves different model families differently:

- ``anthropic``: Claude deployments (Messages API, ``<endpoint>/anthropic/v1/messages``)
- ``openai``:    GPT / Llama / Mistral etc. (chat completions, ``<endpoint>/openai/v1/chat/completions``)

The endpoint, key and deployment name come from environment variables only.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncIterator, Literal, Type, TypeVar

import httpx
import structlog

from app.ai.providers.base import (
    GenerateOptions,
    LLMProvider,
    LLMProviderError,
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

ApiStyle = Literal["anthropic", "openai"]


class AzureFoundryProvider(LLMProvider):
    """LLM provider for models deployed in Azure AI Foundry."""

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        model: str,
        api_style: ApiStyle = "anthropic",
        timeout: int = 120,
        api_version: str = "2023-06-01",
    ) -> None:
        if not endpoint or not api_key or not model:
            raise LLMProviderError(
                "Azure Foundry needs LLM_ENDPOINT, LLM_API_KEY and LLM_MODEL to be set."
            )
        self._endpoint = endpoint.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._style = api_style
        self._timeout = timeout
        self._api_version = api_version
        logger.info("azure_foundry_provider_initialized", model=model, api_style=api_style)

    @property
    def provider_name(self) -> str:
        return "azure_foundry"

    @property
    def model_name(self) -> str:
        return self._model

    # ── request building ────────────────────────────────────────

    def _url(self) -> str:
        if self._style == "anthropic":
            return f"{self._endpoint}/anthropic/v1/messages"
        return f"{self._endpoint}/openai/v1/chat/completions"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._style == "anthropic":
            headers["x-api-key"] = self._api_key
            headers["anthropic-version"] = self._api_version
        else:
            headers["api-key"] = self._api_key
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _payload(self, prompt: str, options: GenerateOptions, stream: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._model,
            "max_tokens": options.max_tokens,
            "temperature": options.temperature,
            "stream": stream,
        }
        if self._style == "anthropic":
            payload["messages"] = [{"role": "user", "content": prompt}]
            if options.system_prompt:
                payload["system"] = options.system_prompt
            if options.stop_sequences:
                payload["stop_sequences"] = options.stop_sequences
        else:
            messages: list[dict[str, str]] = []
            if options.system_prompt:
                messages.append({"role": "system", "content": options.system_prompt})
            messages.append({"role": "user", "content": prompt})
            payload["messages"] = messages
            if options.stop_sequences:
                payload["stop"] = options.stop_sequences
        return payload

    def _parse(self, data: dict[str, Any]) -> tuple[str, int | None, int | None]:
        if self._style == "anthropic":
            text = "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")
            usage = data.get("usage", {})
            return text, usage.get("input_tokens"), usage.get("output_tokens")
        choices = data.get("choices") or [{}]
        text = (choices[0].get("message") or {}).get("content") or ""
        usage = data.get("usage", {})
        return text, usage.get("prompt_tokens"), usage.get("completion_tokens")

    async def _post_with_retry(self, client: httpx.AsyncClient, payload: dict[str, Any]) -> httpx.Response:
        """POST, retrying dropped connections, rate limits (429) and 5xx errors."""
        attempts = 3
        for attempt in range(attempts):
            try:
                resp = await client.post(self._url(), headers=self._headers(), json=payload)
            except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadError):
                if attempt == attempts - 1:
                    raise
                logger.warning("azure_foundry_retry", reason="connection_dropped", attempt=attempt + 1)
                await asyncio.sleep(1 + attempt)
                continue
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < attempts - 1:
                wait = min(float(resp.headers.get("retry-after", 2 ** attempt)), 20)
                logger.warning("azure_foundry_retry", status=resp.status_code, wait_s=wait)
                await asyncio.sleep(wait)
                continue
            return resp
        raise LLMProviderUnavailableError("Azure Foundry retries exhausted")  # unreachable

    # ── interface ───────────────────────────────────────────────

    async def health_check(self) -> bool:
        """A one-token request proves the endpoint, key and deployment are valid."""
        try:
            await self.generate("ping", GenerateOptions(max_tokens=1, temperature=0.0))
            return True
        except Exception as exc:
            logger.warning("azure_foundry_health_check_failed", error=str(exc))
            return False

    async def generate(self, prompt: str, options: GenerateOptions | None = None) -> LLMResponse:
        options = options or GenerateOptions()
        started = time.time()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await self._post_with_retry(client, self._payload(prompt, options, False))
            if resp.status_code != 200:
                raise LLMProviderUnavailableError(f"Azure Foundry returned {resp.status_code}: {resp.text[:300]}")
            text, tokens_in, tokens_out = self._parse(resp.json())
            return LLMResponse(
                content=text,
                model=self._model,
                provider=self.provider_name,
                input_tokens=tokens_in,
                output_tokens=tokens_out,
                latency_ms=(time.time() - started) * 1000,
            )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(f"Azure Foundry request timed out after {self._timeout}s") from exc
        except httpx.RequestError as exc:
            raise LLMProviderUnavailableError(f"Failed to reach Azure Foundry: {exc}") from exc
        except LLMProviderError:
            raise
        except Exception as exc:
            raise LLMProviderError(f"Unexpected Azure Foundry error: {exc}") from exc

    async def stream(self, prompt: str, options: GenerateOptions | None = None) -> AsyncIterator[StreamChunk]:
        options = options or GenerateOptions()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream(
                    "POST", self._url(), headers=self._headers(), json=self._payload(prompt, options, True)
                ) as resp:
                    if resp.status_code != 200:
                        body = (await resp.aread()).decode(errors="replace")
                        raise LLMProviderUnavailableError(f"Azure Foundry returned {resp.status_code}: {body[:300]}")
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if raw == "[DONE]":
                            break
                        try:
                            event = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if self._style == "anthropic":
                            delta = event.get("delta", {}) if event.get("type") == "content_block_delta" else {}
                            piece = delta.get("text", "")
                        else:
                            choices = event.get("choices") or [{}]
                            piece = (choices[0].get("delta") or {}).get("content") or ""
                        if piece:
                            yield StreamChunk(content=piece, model=self._model, provider=self.provider_name)
            yield StreamChunk(content="", is_final=True, model=self._model, provider=self.provider_name)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(f"Azure Foundry streaming timed out after {self._timeout}s") from exc
        except httpx.RequestError as exc:
            raise LLMProviderUnavailableError(f"Failed to reach Azure Foundry: {exc}") from exc

    async def structured_generate(
        self, prompt: str, schema: Type[T], options: GenerateOptions | None = None
    ) -> T:
        """Ask for JSON matching the schema and validate it with Pydantic."""
        options = options or GenerateOptions()
        json_schema = json.dumps(schema.model_json_schema())  # type: ignore[attr-defined]
        wrapped = f"{prompt}\n\nRespond with ONLY a JSON object matching this JSON Schema, no prose:\n{json_schema}"
        response = await self.generate(wrapped, options)
        text = response.content.strip()
        if text.startswith("```"):
            text = text.strip("`").removeprefix("json").strip()
        try:
            return schema.model_validate(json.loads(text))  # type: ignore[attr-defined]
        except Exception as exc:
            raise LLMStructuredOutputError(f"Model output did not match schema: {exc}") from exc

    async def tool_calling(
        self, prompt: str, tools: list[ToolDefinition], options: GenerateOptions | None = None
    ) -> ToolCallResult:
        # The agents execute tools through the MCP gateway, not provider-native
        # function calling, so this is intentionally not implemented yet.
        raise LLMProviderError("Provider-native tool calling is not implemented for Azure Foundry.")
