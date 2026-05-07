"""
HLA Agent — Provider Factory
Creates the correct LLM provider based on configuration.
"""

import logging
from providers.base import LLMProvider
from config import LLM_PROVIDER

logger = logging.getLogger(__name__)

# Registry of available providers
_PROVIDER_MAP = {
    "groq": "providers.groq_provider.GroqProvider",
    "deepseek": "providers.deepseek_provider.DeepSeekProvider",
    "gemini": "providers.gemini_provider.GeminiProvider",
    "ollama": "providers.ollama_provider.OllamaProvider",
}

# Cached provider instance
_provider_instance: LLMProvider | None = None


def get_provider(provider_name: str | None = None) -> LLMProvider:
    """
    Get the LLM provider instance (singleton per provider name).

    Args:
        provider_name: Override provider name. Defaults to config.LLM_PROVIDER.

    Returns:
        LLMProvider instance
    """
    global _provider_instance

    name = provider_name or LLM_PROVIDER

    # Return cached if same provider
    if _provider_instance is not None and not provider_name:
        return _provider_instance

    if name not in _PROVIDER_MAP:
        raise ValueError(
            f"Unknown provider: '{name}'. "
            f"Available: {list(_PROVIDER_MAP.keys())}"
        )

    # Dynamic import to avoid loading unused SDKs
    module_path, class_name = _PROVIDER_MAP[name].rsplit(".", 1)

    import importlib
    module = importlib.import_module(module_path)
    provider_class = getattr(module, class_name)

    instance = provider_class()
    logger.info(f"Initialized LLM provider: {instance.provider_name}")

    if not provider_name:
        _provider_instance = instance

    return instance


def get_provider_name() -> str:
    """Get the current provider name from config."""
    return LLM_PROVIDER


__all__ = ["get_provider", "get_provider_name", "LLMProvider"]
