"""
HLA Agent — LLM Provider Base Class
Abstract interface that all LLM providers must implement.
"""

from abc import ABC, abstractmethod
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def generate(self, prompt: str, model: str, options: dict) -> str:
        """
        Generate text from a prompt using the specified model.

        Args:
            prompt: The full prompt string
            model: Model identifier (provider-specific)
            options: Generation options (temperature, max_tokens, etc.)

        Returns:
            Generated text string

        Raises:
            Exception: If generation fails
        """
        pass

    @abstractmethod
    def list_models(self) -> list[str]:
        """
        List available models for this provider.

        Returns:
            List of model name strings
        """
        pass

    @abstractmethod
    def check_available(self, models: list[str]) -> dict[str, bool]:
        """
        Check which models are available / accessible.

        Args:
            models: List of model names to check

        Returns:
            Dict of model_name → bool (available or not)
        """
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider name."""
        pass
