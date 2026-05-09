"""
HLA Agent — DeepSeek Provider
Open-source LLM via DeepSeek API (OpenAI-compatible).
Supports: DeepSeek-V3 (deepseek-chat) — excellent for architecture & code.
"""

import logging
from openai import OpenAI

from providers.base import LLMProvider
from config import DEEPSEEK_API_KEY

logger = logging.getLogger(__name__)

DEEPSEEK_BASE_URL = "https://api.deepseek.com"


class DeepSeekProvider(LLMProvider):
    """DeepSeek provider — uses OpenAI-compatible API."""

    def __init__(self):
        if not DEEPSEEK_API_KEY:
            raise ValueError(
                "DEEPSEEK_API_KEY not set. Get a key at https://platform.deepseek.com"
            )
        self.client = OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL,
        )

    @property
    def provider_name(self) -> str:
        return "DeepSeek"

    def generate(self, prompt: str, model: str, options: dict) -> str:
        """Generate architecture via DeepSeek API."""
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
            max_tokens=options.get("max_tokens", 4000),
        )
        return response.choices[0].message.content.strip()

    def list_models(self) -> list[str]:
        """List available DeepSeek models."""
        try:
            models = self.client.models.list()
            return [m.id for m in models.data]
        except Exception as e:
            logger.error(f"Failed to list DeepSeek models: {e}")
            return ["deepseek-chat", "deepseek-reasoner"]

    def check_available(self, models: list[str]) -> dict[str, bool]:
        """Check model availability — if API key works, models are available."""
        try:
            available = set(self.list_models())
            return {m: m in available for m in models}
        except Exception:
            return {m: bool(DEEPSEEK_API_KEY) for m in models}
