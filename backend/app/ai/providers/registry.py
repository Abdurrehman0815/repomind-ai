"""
RepoMind AI — LLM Provider Registry

Resolves the configured LLM provider at runtime.

Usage:
    from app.ai.providers.registry import get_llm_provider

    provider = get_llm_provider()
    response = await provider.generate(prompt)
"""
from functools import lru_cache

from app.ai.providers.base import LLMProvider
from app.core.config import get_settings


@lru_cache(maxsize=1)
def get_llm_provider() -> LLMProvider:
    """
    Return the configured LLM provider instance.

    The provider is selected based on the LLM_PROVIDER environment variable.

    Supported values:
        - 'ollama'  → LocalOllamaProvider (available from Phase 9)
        - 'bedrock' → BedrockProvider     (available from Phase 32)

    The rest of the application must call this function, never instantiate
    providers directly.
    """
    settings = get_settings()

    if settings.llm_provider == "ollama":
        from app.ai.providers.ollama import LocalOllamaProvider
        return LocalOllamaProvider(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            timeout=settings.ollama_timeout,
            max_tokens=settings.ollama_max_tokens,
            keep_alive=settings.ollama_keep_alive,
            num_ctx=settings.ollama_num_ctx,
        )
    elif settings.llm_provider == "azure_foundry":
        from app.ai.providers.azure_foundry import AzureFoundryProvider
        return AzureFoundryProvider(
            endpoint=settings.llm_endpoint,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            api_style=settings.llm_api_style,
            timeout=settings.llm_timeout,
        )
    elif settings.llm_provider == "bedrock":
        # Bedrock implementation is added in Phase 32.
        # Do not implement or import before all local phases pass.
        raise NotImplementedError(
            "Amazon Bedrock provider is not yet implemented. "
            "Set LLM_PROVIDER=ollama for local operation."
        )
    else:
        raise ValueError(
            f"Unknown LLM provider: '{settings.llm_provider}'. "
            f"Supported values: 'ollama' (and 'bedrock' in Phase 32+)."
        )
