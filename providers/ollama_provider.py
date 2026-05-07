"""
HLA Agent — Ollama Provider (Local LLM)
Backward-compatible provider for local Ollama inference.
Supports: Any Ollama-installed model (llama3.1, mistral, qwen3, etc.)
"""

import logging
import ollama

from providers.base import LLMProvider
from config import OLLAMA_HOST, GENERATION_OPTIONS

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """Ollama local provider for GPU-accelerated inference."""

    def __init__(self):
        # Ollama client uses OLLAMA_HOST env var automatically
        pass

    @property
    def provider_name(self) -> str:
        return "Ollama (Local)"

    def generate(self, prompt: str, model: str, options: dict) -> str:
        """Generate architecture via local Ollama."""
        # Map generic options to Ollama-specific options
        ollama_options = {
            "temperature": options.get("temperature", 0.7),
            "num_ctx": 4096,
            "num_predict": options.get("max_tokens", 3000),
        }

        response = ollama.generate(
            model=model,
            prompt=prompt,
            options=ollama_options,
            stream=False,
        )
        return response.response.strip()

    def list_models(self) -> list[str]:
        """List locally installed Ollama models."""
        try:
            installed = ollama.list()
            return [m.model.split(":")[0] for m in installed.models]
        except Exception as e:
            logger.error(f"Failed to list Ollama models: {e}")
            return []

    def check_available(self, models: list[str]) -> dict[str, bool]:
        """Check which models are installed locally in Ollama."""
        try:
            installed = ollama.list()
            installed_names = set()
            for model_info in installed.models:
                name = model_info.model
                base_name = name.split(":")[0]
                installed_names.add(base_name)
                installed_names.add(name)

            availability = {}
            for model in models:
                base = model.split(":")[0]
                availability[model] = base in installed_names or model in installed_names
            return availability
        except Exception as e:
            logger.error(f"Failed to check Ollama availability: {e}")
            return {m: False for m in models}
