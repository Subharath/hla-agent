"""
HLA Agent — SCI: Structural Clarity Index

Formula: SCI = valid_components / total_components

A component is "valid" if:
  (a) name ends with a recognized role suffix
  (b) responsibility has at least MIN_RESPONSIBILITY_WORDS words
"""

import logging
from config import VALID_COMPONENT_SUFFIXES, MIN_RESPONSIBILITY_WORDS

logger = logging.getLogger(__name__)


def _has_valid_suffix(name: str) -> bool:
    """Check if component name ends with a recognized architectural suffix."""
    name_lower = name.lower().strip()
    for suffix in VALID_COMPONENT_SUFFIXES:
        if name_lower.endswith(suffix.lower()):
            return True
    return False


def _has_valid_responsibility(responsibility: str) -> bool:
    """Check if responsibility is descriptive enough."""
    words = responsibility.strip().split()
    return len(words) >= MIN_RESPONSIBILITY_WORDS


def compute_sci(architecture: dict) -> dict:
    """
    Compute Structural Clarity Index.

    Args:
        architecture: Parsed architecture dict with 'components'

    Returns:
        {
            "score": float (0.0 - 1.0),
            "valid": int,
            "total": int,
            "component_details": [{ name, valid_suffix, valid_responsibility, valid }]
        }
    """
    components = architecture.get("components", [])

    if not components:
        return {"score": 0.0, "valid": 0, "total": 0, "component_details": []}

    details = []
    valid_count = 0

    for comp in components:
        name = comp.get("name", "")
        responsibility = comp.get("responsibility", "")

        has_suffix = _has_valid_suffix(name)
        has_resp = _has_valid_responsibility(responsibility)
        is_valid = has_suffix and has_resp

        if is_valid:
            valid_count += 1

        details.append({
            "name": name,
            "valid_suffix": has_suffix,
            "valid_responsibility": has_resp,
            "valid": is_valid,
            "word_count": len(responsibility.strip().split()),
        })

    total = len(components)
    score = valid_count / total if total > 0 else 0.0

    logger.info(f"SCI: {score:.3f} | Valid: {valid_count}/{total}")

    return {
        "score": round(score, 4),
        "valid": valid_count,
        "total": total,
        "component_details": details,
    }
