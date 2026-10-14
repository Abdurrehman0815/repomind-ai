"""
RepoMind AI — AI Providers Package
"""
from .embedding_base import EmbeddingProvider, EmbeddingOptions, EmbeddingResponse, EmbeddingProviderError, EmbeddingProviderUnavailableError, EmbeddingProviderInvalidInputError
from .embedding_registry import get_embedding_provider
from .local_embedding import LocalEmbeddingProvider
from .base import LLMResponse, GenerateOptions, StreamChunk, ToolDefinition, ToolCallResult, LLMProvider, LLMProviderError, LLMProviderUnavailableError, LLMStructuredOutputError, LLMTimeoutError
from .ollama import LocalOllamaProvider
from .registry import get_llm_provider

__all__ = [
    # Embedding providers
    "EmbeddingProvider",
    "EmbeddingOptions",
    "EmbeddingResponse",
    "EmbeddingProviderError",
    "EmbeddingProviderUnavailableError",
    "EmbeddingProviderInvalidInputError",
    "get_embedding_provider",
    "LocalEmbeddingProvider",
    # LLM providers
    "LLMResponse",
    "GenerateOptions",
    "StreamChunk",
    "ToolDefinition",
    "ToolCallResult",
    "LLMProvider",
    "LLMProviderError",
    "LLMProviderUnavailableError",
    "LLMStructuredOutputError",
    "LLMTimeoutError",
    "get_llm_provider",
    "LocalOllamaProvider"
]