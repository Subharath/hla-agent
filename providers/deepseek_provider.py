"""
HLA Agent — DeepSeek Provider
Open-source LLM via DeepSeek API (OpenAI-compatible).
Supports: DeepSeek-V4 (deepseek-v4-flash) — excellent for architecture & code.
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
            return ["deepseek-v4-flash", "deepseek-v4-pro"]

    def check_available(self, models: list[str]) -> dict[str, bool]:
        """Check model availability including a lightweight generation probe.

        DeepSeek can return model lists even when billing is exhausted. We run a
        minimal completion request to verify the account can actually generate.
        """
        try:
            available = set(self.list_models())
            mapped = [m for m in models if m in available]
            if not mapped:
                return {m: False for m in models}

            probe_model = mapped[0]
            try:
                self.client.chat.completions.create(
                    model=probe_model,
                    messages=[{"role": "user", "content": "ping"}],
                    temperature=0,
                    max_tokens=1,
                )
            except Exception as e:
                msg = str(e).lower()
                status = getattr(e, "status_code", None)
                if status == 402 or "insufficient balance" in msg:
                    logger.warning("DeepSeek unavailable due to insufficient balance.")
                else:
                    logger.warning(f"DeepSeek availability probe failed: {e}")
                return {m: False for m in models}

            return {m: m in available for m in models}
        except Exception:
            return {m: False for m in models}
