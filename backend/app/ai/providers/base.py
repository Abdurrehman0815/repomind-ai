"""
RepoMind AI — LLM Provider Abstract Base

All LLM interactions go through this interface.
Application code never calls Ollama or Bedrock directly.

Usage:
    provider = get_llm_provider()
    response = await provider.generate(prompt)
"""
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class GenerateOptions(BaseModel):
    """Options for text generation."""
    max_tokens: int = 4096
    temperature: float = 0.1
    stop_sequences: list[str] = []
    system_prompt: str | None = None


class LLMResponse(BaseModel):
    """Response from an LLM provider."""
    content: str
    model: str
    provider: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: float | None = None
    # Cost is 0.0 for local providers; real cost for cloud providers
    estimated_cost_usd: float = 0.0


class StreamChunk(BaseModel):
    """A single chunk in a streaming response."""
    content: str
    is_final: bool = False
    model: str | None = None
    provider: str | None = None


class ToolDefinition(BaseModel):
    """Definition of a tool that the LLM may call."""
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema object


class ToolCallResult(BaseModel):
    """Result of a tool-calling LLM response."""
    content: str | None = None
    tool_calls: list[dict[str, Any]] = []
    model: str
    provider: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: float | None = None
    estimated_cost_usd: float = 0.0


class LLMProvider(ABC):
    """
    Abstract base class for all LLM providers.

    Implementations:
        - LocalOllamaProvider  (Phase 9)
        - BedrockProvider      (Phase 32+)

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

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the provider is reachable and the model is available.
        Returns True if healthy, False otherwise.
        """
        ...

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        options: GenerateOptions | None = None,
    ) -> LLMResponse:
        """
        Generate a text response from the given prompt.

        Args:
            prompt: The user prompt
            options: Generation options (max_tokens, temperature, etc.)

        Returns:
            LLMResponse with content and metadata
        """
        ...

    @abstractmethod
    async def stream(
        self,
        prompt: str,
        options: GenerateOptions | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream a response token by token.

        Args:
            prompt: The user prompt
            options: Generation options

        Yields:
            StreamChunk objects; final chunk has is_final=True
        """
        ...

    @abstractmethod
    async def structured_generate(
        self,
        prompt: str,
        schema: Type[T],
        options: GenerateOptions | None = None,
    ) -> T:
        """
        Generate a structured response conforming to a Pydantic schema.

        The provider must return valid JSON that can be parsed into the schema.

        Args:
            prompt: The user prompt
            schema: Pydantic model class defining the expected structure
            options: Generation options

        Returns:
            An instance of the provided schema

        Raises:
            LLMStructuredOutputError: If the output cannot be parsed
        """
        ...

    @abstractmethod
    async def tool_calling(
        self,
        prompt: str,
        tools: list[ToolDefinition],
        options: GenerateOptions | None = None,
    ) -> ToolCallResult:
        """
        Generate a response that may include tool calls.

        Args:
            prompt: The user prompt
            tools: Available tool definitions
            options: Generation options

        Returns:
            ToolCallResult with content and/or tool_calls
        """
        ...


class LLMProviderError(Exception):
    """Base exception for all LLM provider errors."""
    pass


class LLMProviderUnavailableError(LLMProviderError):
    """Provider is not reachable."""
    pass


class LLMStructuredOutputError(LLMProviderError):
    """Provider returned output that could not be parsed into the expected schema."""
    pass


class LLMTimeoutError(LLMProviderError):
    """Provider call timed out."""
    pass
