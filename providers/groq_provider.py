"""
HLA Agent — Groq Provider
Open-source LLM inference via Groq Cloud (free tier available).
Supports: Llama 3.3 70B, Mixtral 8x7B, etc.
"""

import logging
from groq import Groq

from providers.base import LLMProvider
from config import GROQ_API_KEY

logger = logging.getLogger(__name__)


class GroqProvider(LLMProvider):
    """Groq Cloud provider for fast open-source LLM inference."""

    def __init__(self):
        if not GROQ_API_KEY:
            raise ValueError(
                "GROQ_API_KEY not set. Get a free key at https://console.groq.com"
            )
        self.client = Groq(api_key=GROQ_API_KEY)

    @property
    def provider_name(self) -> str:
        return "Groq"

    def generate(self, prompt: str, model: str, options: dict) -> str:
        """Generate architecture via Groq API."""
        response = self.client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert software architect. Respond ONLY with valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=options.get("temperature", 0.7),
            max_completion_tokens=options.get("max_tokens", 4000),
        )
        return response.choices[0].message.content.strip()

    def list_models(self) -> list[str]:
        """List available Groq models."""
        try:
            models = self.client.models.list()
            return [m.id for m in models.data]
        except Exception as e:
            logger.error(f"Failed to list Groq models: {e}")
            return []

    def check_available(self, models: list[str]) -> dict[str, bool]:
        """Check which models are available on Groq."""
        try:
            available = set(self.list_models())
            return {m: m in available for m in models}
        except Exception:
            # If API key is valid, models should be available
            return {m: bool(GROQ_API_KEY) for m in models}
