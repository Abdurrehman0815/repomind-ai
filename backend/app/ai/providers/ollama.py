"""
RepoMind AI — Ollama LLM Provider

Full implementation for Phase 9.
Implements the LLM provider interface for Ollama local inference.
"""
import json
import time
from typing import AsyncIterator, Type, TypeVar

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


class LocalOllamaProvider(LLMProvider):
    """
    Ollama local LLM provider.

    Implements text generation, streaming, structured output, and tool calling
    using the Ollama HTTP API.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.2",
        timeout: int = 120,
        max_tokens: int = 4096,
        keep_alive: str = "30m",
        num_ctx: int = 6144,
    ) -> None:
        self._keep_alive = keep_alive
        self._num_ctx = num_ctx
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._max_tokens = max_tokens
        logger.info(
            "ollama_provider_initialized",
            base_url=self._base_url,
            model=self._model,
            timeout=timeout,
            max_tokens=max_tokens,
        )

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._model

    async def health_check(self) -> bool:
        """Check if Ollama server is reachable and the model is available."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Check if server is reachable
                resp = await client.get(f"{self._base_url}/api/version")
                if resp.status_code != 200:
                    return False

                # Check if the specific model is available
                resp = await client.get(f"{self._base_url}/api/tags")
                if resp.status_code != 200:
                    return False

                data = resp.json()
                models = [m["name"] for m in data.get("models", [])]
                # Check if our model is in the list (with or without tag)
                model_available = any(
                    m.startswith(self._model) or m == self._model
                    for m in models
                )
                return model_available
        except Exception as exc:
            logger.warning("ollama_health_check_failed", error=str(exc))
            return False

    async def generate(
        self,
        prompt: str,
        options: GenerateOptions | None = None,
    ) -> LLMResponse:
        """
        Generate a text response from the given prompt using Ollama.

        Args:
            prompt: The user prompt
            options: Generation options (max_tokens, temperature, etc.)

        Returns:
            LLMResponse with content and metadata
        """
        start_time = time.time()
        options = options or GenerateOptions()

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                payload = {
                    "model": self._model,
                    "prompt": prompt,
                    "stream": False,
                    "keep_alive": self._keep_alive,
                    "options": {
                        "temperature": options.temperature,
                        "num_predict": options.max_tokens,
                        "num_ctx": self._num_ctx,
                    }
                }

                if options.system_prompt:
                    payload["system"] = options.system_prompt

                if options.stop_sequences:
                    payload["options"]["stop"] = options.stop_sequences

                resp = await client.post(
                    f"{self._base_url}/api/generate",
                    json=payload
                )

                if resp.status_code != 200:
                    raise LLMProviderUnavailableError(
                        f"Ollama API returned status {resp.status_code}: {resp.text}"
                    )

                data = resp.json()

                # Calculate latency
                latency_ms = (time.time() - start_time) * 1000

                return LLMResponse(
                    content=data.get("response", ""),
                    model=self._model,
                    provider=self.provider_name,
                    input_tokens=None,  # Ollama doesn't provide token counts in standard API
                    output_tokens=None,
                    latency_ms=latency_ms,
                    estimated_cost_usd=0.0  # Local model has no cost
                )

        except httpx.TimeoutException as exc:
            logger.error("ollama_generate_timeout", error=str(exc))
            raise LLMTimeoutError(f"Ollama request timed out after {self._timeout}s") from exc
        except httpx.RequestError as exc:
            logger.error("ollama_generate_request_error", error=str(exc))
            raise LLMProviderUnavailableError(f"Failed to connect to Ollama: {str(exc)}") from exc
        except Exception as exc:
            logger.error("ollama_generate_unexpected_error", error=str(exc))
            raise LLMProviderError(f"Unexpected error during generation: {str(exc)}") from exc

    async def stream(
        self,
        prompt: str,
        options: GenerateOptions | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream a response token by token from Ollama.

        Args:
            prompt: The user prompt
            options: Generation options

        Yields:
            StreamChunk objects; final chunk has is_final=True
        """
        start_time = time.time()
        options = options or GenerateOptions()

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                payload = {
                    "model": self._model,
                    "prompt": prompt,
                    "stream": True,
                    "keep_alive": self._keep_alive,
                    "options": {
                        "temperature": options.temperature,
                        "num_predict": options.max_tokens,
                        "num_ctx": self._num_ctx,
                    }
                }

                if options.system_prompt:
                    payload["system"] = options.system_prompt

                if options.stop_sequences:
                    payload["options"]["stop"] = options.stop_sequences

                async with client.stream(
                    "POST",
                    f"{self._base_url}/api/generate",
                    json=payload
                ) as resp:
                    if resp.status_code != 200:
                        error_text = await resp.aread()
                        raise LLMProviderUnavailableError(
                            f"Ollama API returned status {resp.status_code}: {error_text.decode()}"
                        )

                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue

                        try:
                            data = json.loads(line)
                            chunk_content = data.get("response", "")

                            yield StreamChunk(
                                content=chunk_content,
                                is_final=data.get("done", False),
                                model=self._model,
                                provider=self.provider_name
                            )

                            if data.get("done", False):
                                # Calculate final latency
                                latency_ms = (time.time() - start_time) * 1000
                                # Update the final chunk with latency
                                yield StreamChunk(
                                    content="",
                                    is_final=True,
                                    model=self._model,
                                    provider=self.provider_name
                                )
                                break

                        except json.JSONDecodeError:
                            logger.warning("ollama_stream_invalid_json", line=line)
                            continue

        except httpx.TimeoutException as exc:
            logger.error("ollama_stream_timeout", error=str(exc))
            raise LLMTimeoutError(f"Ollama streaming timed out after {self._timeout}s") from exc
        except httpx.RequestError as exc:
            logger.error("ollama_stream_request_error", error=str(exc))
            raise LLMProviderUnavailableError(f"Failed to connect to Ollama: {str(exc)}") from exc
        except Exception as exc:
            logger.error("ollama_stream_unexpected_error", error=str(exc))
            raise LLMProviderError(f"Unexpected error during streaming: {str(exc)}") from exc

    async def structured_generate(
        self,
        prompt: str,
        schema: Type[T],
        options: GenerateOptions | None = None,
    ) -> T:
        """
        Generate a structured response conforming to a Pydantic schema using Ollama's JSON mode.

        Args:
            prompt: The user prompt
            schema: Pydantic model class defining the expected structure
            options: Generation options

        Returns:
            An instance of the provided schema

        Raises:
            LLMStructuredOutputError: If the output cannot be parsed
        """
        start_time = time.time()
        options = options or GenerateOptions()

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                payload = {
                    "model": self._model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",  # Enable JSON mode
                    "options": {
                        "temperature": options.temperature,
                        "num_predict": options.max_tokens,
                        "num_ctx": self._num_ctx,
                    }
                }

                if options.system_prompt:
                    payload["system"] = options.system_prompt

                if options.stop_sequences:
                    payload["options"]["stop"] = options.stop_sequences

                resp = await client.post(
                    f"{self._base_url}/api/generate",
                    json=payload
                )

                if resp.status_code != 200:
                    raise LLMProviderUnavailableError(
                        f"Ollama API returned status {resp.status_code}: {resp.text}"
                    )

                data = resp.json()
                response_text = data.get("response", "{}")

                # Calculate latency
                latency_ms = (time.time() - start_time) * 1000

                # Parse the JSON response
                try:
                    parsed_data = json.loads(response_text)
                    # Validate against the Pydantic schema
                    validated_instance = schema.model_validate(parsed_data)
                    return validated_instance
                except (json.JSONDecodeError, Exception) as exc:
                    logger.error(
                        "ollama_structured_generate_parse_error",
                        response_text=response_text[:200],
                        error=str(exc)
                    )
                    raise LLMStructuredOutputError(
                        f"Failed to parse structured output: {str(exc)}"
                    ) from exc

        except httpx.TimeoutException as exc:
            logger.error("ollama_structured_generate_timeout", error=str(exc))
            raise LLMTimeoutError(f"Ollama request timed out after {self._timeout}s") from exc
        except httpx.RequestError as exc:
            logger.error("ollama_structured_generate_request_error", error=str(exc))
            raise LLMProviderUnavailableError(f"Failed to connect to Ollama: {str(exc)}") from exc
        except Exception as exc:
            logger.error("ollama_structured_generate_unexpected_error", error=str(exc))
            raise LLMProviderError(f"Unexpected error during structured generation: {str(exc)}") from exc

    async def tool_calling(
        self,
        prompt: str,
        tools: list[ToolDefinition],
        options: GenerateOptions | None = None,
    ) -> ToolCallResult:
        """
        Generate a response that may include tool calls using Ollama.

        Args:
            prompt: The user prompt
            tools: Available tool definitions
            options: Generation options

        Returns:
            ToolCallResult with content and/or tool_calls
        """
        start_time = time.time()
        options = options or GenerateOptions()

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                # Convert tools to Ollama format
                ollama_tools = []
                for tool in tools:
                    ollama_tool = {
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.parameters
                        }
                    }
                    ollama_tools.append(ollama_tool)

                payload = {
                    "model": self._model,
                    "prompt": prompt,
                    "stream": False,
                    "tools": ollama_tools,
                    "options": {
                        "temperature": options.temperature,
                        "num_predict": options.max_tokens,
                        "num_ctx": self._num_ctx,
                    }
                }

                if options.system_prompt:
                    payload["system"] = options.system_prompt

                if options.stop_sequences:
                    payload["options"]["stop"] = options.stop_sequences

                resp = await client.post(
                    f"{self._base_url}/api/generate",
                    json=payload
                )

                if resp.status_code != 200:
                    raise LLMProviderUnavailableError(
                        f"Ollama API returned status {resp.status_code}: {resp.text}"
                    )

                data = resp.json()

                # Calculate latency
                latency_ms = (time.time() - start_time) * 1000

                # Parse response for potential tool calls
                response_text = data.get("response", "")
                tool_calls = []

                # Try to extract tool calls from the response
                # Ollama may return tool calls in various formats
                try:
                    # Look for JSON-like tool call patterns in the response
                    # Simple pattern detection for tool calls
                    # This is a simplified implementation - in practice,
                    # Ollama's tool calling support varies by model
                    if "{" in response_text and "}" in response_text:
                        # Attempt to parse as JSON if it looks like a tool call
                        stripped = response_text.strip()
                        if stripped.startswith("{") and stripped.endswith("}"):
                            try:
                                parsed = json.loads(stripped)
                                if "name" in parsed and "arguments" in parsed:
                                    tool_calls.append({
                                        "name": parsed["name"],
                                        "arguments": parsed["arguments"] if isinstance(parsed["arguments"], dict) else json.loads(parsed["arguments"])
                                    })
                            except (json.JSONDecodeError, KeyError):
                                pass  # Not a tool call, treat as regular response
                except Exception:
                    pass  # Continue with regular response if parsing fails

                return ToolCallResult(
                    content=response_text if not tool_calls else None,
                    tool_calls=tool_calls,
                    model=self._model,
                    provider=self.provider_name,
                    input_tokens=None,
                    output_tokens=None,
                    latency_ms=latency_ms,
                    estimated_cost_usd=0.0
                )

        except httpx.TimeoutException as exc:
            logger.error("ollama_tool_calling_timeout", error=str(exc))
            raise LLMTimeoutError(f"Ollama request timed out after {self._timeout}s") from exc
        except httpx.RequestError as exc:
            logger.error("ollama_tool_calling_request_error", error=str(exc))
            raise LLMProviderUnavailableError(f"Failed to connect to Ollama: {str(exc)}") from exc
        except Exception as exc:
            logger.error("ollama_tool_calling_unexpected_error", error=str(exc))
            raise LLMProviderError(f"Unexpected error during tool calling: {str(exc)}") from exc
