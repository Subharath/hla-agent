"""
HLA Agent — Multi-Model LLM Generator
Uses the provider abstraction to call any configured LLM backend.
Generates architecture candidates with retries and timeouts.
"""

import time
import json
import logging
from typing import Optional

from config import (
    MODELS,
    CANDIDATES_PER_MODEL,
    GENERATION_OPTIONS,
    MAX_GENERATION_RETRIES,
)
from providers import get_provider_for_model

logger = logging.getLogger(__name__)


def _is_non_retryable_error(error: Exception) -> bool:
    """Return True for errors that should fail fast without retries."""
    status = getattr(error, "status_code", None)
    text = str(error).lower()

    if status in {400, 401, 402, 403, 404}:
        return True

    non_retryable_markers = [
        "insufficient balance",
        "invalid api key",
        "authentication",
        "permission",
        "not found",
        "invalid_request_error",
    ]
    return any(marker in text for marker in non_retryable_markers)


class GenerationResult:
    """Holds the result of one LLM generation attempt."""

    def __init__(self, model: str, candidate_num: int, raw_text: str,
                 success: bool, duration_ms: float, error: Optional[str] = None):
        self.model = model
        self.candidate_num = candidate_num
        self.raw_text = raw_text
        self.success = success
        self.duration_ms = duration_ms
        self.error = error

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "candidate_num": self.candidate_num,
            "raw_text": self.raw_text,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


def generate_single(model: str, prompt: str, candidate_num: int) -> GenerationResult:
    """
    Generate a single architecture candidate from one model.

    Args:
        model: Model name (e.g., "gemini-2.0-flash", "llama-3.3-70b-versatile")
        prompt: Full structured prompt
        candidate_num: Which candidate number this is (1-based)

    Returns:
        GenerationResult with raw text or error
    """
    provider = get_provider_for_model(model)
    last_error = "Unknown error"

    for attempt in range(1, MAX_GENERATION_RETRIES + 1):
        try:
            logger.info(
                f"[{provider.provider_name}/{model}] Generating candidate {candidate_num}, "
                f"attempt {attempt}/{MAX_GENERATION_RETRIES}..."
            )

            start_time = time.time()

            raw_text = provider.generate(prompt, model, GENERATION_OPTIONS)

            duration_ms = (time.time() - start_time) * 1000

            if not raw_text:
                logger.warning(f"[{model}] Empty response on attempt {attempt}")
                continue

            logger.info(
                f"[{model}] Candidate {candidate_num} generated in {duration_ms:.0f}ms "
                f"({len(raw_text)} chars)"
            )

            return GenerationResult(
                model=model,
                candidate_num=candidate_num,
                raw_text=raw_text,
                success=True,
                duration_ms=duration_ms,
            )

        except Exception as e:
            last_error = str(e)
            logger.error(f"[{model}] Attempt {attempt} failed: {e}")

            if _is_non_retryable_error(e):
                logger.error(f"[{model}] Non-retryable error detected, aborting retries.")
                break

            if attempt < MAX_GENERATION_RETRIES:
                time.sleep(2 * attempt)  # Exponential backoff

    return GenerationResult(
        model=model,
        candidate_num=candidate_num,
        raw_text="",
        success=False,
        duration_ms=0,
        error=last_error,
    )


def generate_all(requirements: dict, models: list = None,
                 candidates_per_model: int = None,
                 progress_callback=None) -> list[GenerationResult]:
    """
    Generate architecture candidates from all configured models.

    Args:
        requirements: Requirements dict
        models: List of model names (defaults to config.MODELS)
        candidates_per_model: How many candidates per model (defaults to config)
        progress_callback: Optional callback(model, candidate_num, total, status)

    Returns:
        List of GenerationResult objects
    """
    models = models or MODELS
    candidates_per_model = candidates_per_model or CANDIDATES_PER_MODEL

    results = []
    total = len(models) * candidates_per_model
    current = 0

    from prompt.builder import build_architecture_prompt

    for model in models:
        for candidate_num in range(1, candidates_per_model + 1):
            current += 1

            if progress_callback:
                progress_callback(model, candidate_num, total, "generating")

            # Dynamically build prompt per candidate_num for ATAM diversity
            prompt = build_architecture_prompt(requirements, candidate_num=candidate_num)
            result = generate_single(model, prompt, candidate_num)
            results.append(result)

            if progress_callback:
                status = "success" if result.success else "failed"
                progress_callback(model, candidate_num, total, status)

    successful = sum(1 for r in results if r.success)
    logger.info(
        f"Generation complete: {successful}/{total} candidates generated successfully"
    )

    return results


def regenerate_single(model: str, prompt: str, candidate_num: int,
                      feedback: str) -> GenerationResult:
    """
    Regenerate a single candidate with feedback appended to the prompt.

    Args:
        model: Model name
        prompt: Original structured prompt
        candidate_num: Candidate number
        feedback: Feedback string from evaluation

    Returns:
        GenerationResult with improved architecture (hopefully)
    """
    enhanced_prompt = (
        f"{prompt}\n\n"
        f"⚠️ IMPORTANT — PREVIOUS ATTEMPT WAS REJECTED. Address these issues:\n"
        f"{feedback}\n"
        f"Generate an IMPROVED architecture that fixes these specific problems.\n"
        f"RESPOND WITH ONLY THE JSON. NO OTHER TEXT."
    )

    return generate_single(model, enhanced_prompt, candidate_num)


def check_models_available(models: list = None) -> dict:
    """
    Check which models are available by querying their specific providers.

    Returns:
        Dict of model_name → bool (available or not)
    """
    models = models or MODELS
    result = {}
    for m in models:
        try:
            provider = get_provider_for_model(m)
            # Call check_available on the specific provider for this model
            avail = provider.check_available([m])
            result[m] = avail.get(m, False)
        except Exception as e:
            logger.error(f"Failed to check model availability for {m}: {e}")
            result[m] = False
    return result

