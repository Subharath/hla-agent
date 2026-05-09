"""
HLA Agent — Google Gemini Provider
Commercial LLM via Google Gemini API (free tier available).
Supports: Gemini 2.0 Flash — fast, excellent structured output.
"""

import logging
from google import genai
from google.genai import types

from providers.base import LLMProvider
from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):
    """Google Gemini provider — commercial LLM with free tier."""

    def __init__(self):
        if not GEMINI_API_KEY:
            raise ValueError(
                "GEMINI_API_KEY not set. Get a free key at https://aistudio.google.com/apikey"
            )
        self.client = genai.Client(api_key=GEMINI_API_KEY)

    @property
    def provider_name(self) -> str:
        return "Google Gemini"

    def generate(self, prompt: str, model: str, options: dict) -> str:
        """Generate architecture via Gemini API."""
        full_prompt = (
            "You are an expert software architect. Respond ONLY with valid JSON.\n\n"
            + prompt
        )
        response = self.client.models.generate_content(
            model=model,
            contents=full_prompt,
            config=types.GenerateContentConfig(
                temperature=options.get("temperature", 0.7),
                max_output_tokens=options.get("max_tokens", 4000),
            ),
        )
        return response.text.strip()

    def list_models(self) -> list[str]:
        """List available Gemini models."""
        try:
            models = self.client.models.list()
            return [m.name for m in models]
        except Exception as e:
            logger.error(f"Failed to list Gemini models: {e}")
            return ["gemini-2.0-flash", "gemini-2.0-flash-lite"]

    def check_available(self, models: list[str]) -> dict[str, bool]:
        """Check model availability — if API key works, models are available."""
        try:
            # Quick validation: list models to verify API key
            available = set(self.list_models())
            result = {}
            for m in models:
                # Gemini model names can be "models/gemini-2.0-flash" or just "gemini-2.0-flash"
                result[m] = m in available or f"models/{m}" in available
            return result
        except Exception:
            return {m: bool(GEMINI_API_KEY) for m in models}
