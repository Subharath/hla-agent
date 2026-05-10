"""
HLA Agent — Provider Factory
Creates the correct LLM provider based on configuration.
"""

import logging
from providers.base import LLMProvider
from config import LLM_PROVIDER, PROVIDER_MODELS

logger = logging.getLogger(__name__)

# Registry of available providers
_PROVIDER_MAP = {
    "groq": "providers.groq_provider.GroqProvider",
    "deepseek": "providers.deepseek_provider.DeepSeekProvider",
    "gemini": "providers.gemini_provider.GeminiProvider",
    "ollama": "providers.ollama_provider.OllamaProvider",
}

# Cached provider instances
_provider_instances: dict[str, LLMProvider] = {}


def get_provider(provider_name: str | None = None) -> LLMProvider:
    """
    Get the LLM provider instance (singleton per provider name).

    Args:
        provider_name: Override provider name. Defaults to config.LLM_PROVIDER.

    Returns:
        LLMProvider instance
    """
    global _provider_instances

    name = provider_name or LLM_PROVIDER

    # Return cached if already instantiated
    if name in _provider_instances:
        return _provider_instances[name]

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

    _provider_instances[name] = instance
    return instance


def get_provider_for_model(model_name: str) -> LLMProvider:
    """
    Looks up which provider supports the given model and returns its instance.
    """
    for provider, models in PROVIDER_MODELS.items():
        if model_name in models:
            return get_provider(provider)
    
    logger.warning(f"Model '{model_name}' not mapped to a provider. Falling back to default: {LLM_PROVIDER}")
    return get_provider(LLM_PROVIDER)


def get_provider_name() -> str:
    """Get the current default provider name from config."""
    return LLM_PROVIDER


__all__ = ["get_provider", "get_provider_for_model", "get_provider_name", "LLMProvider"]
