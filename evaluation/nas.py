"""
HLA Agent — NAS: NFR Alignment Score

Formula: NAS = Σ(support_scores) / total_NFRs

For each NFR, scan all components for evidence keywords that indicate
the architecture supports that quality attribute.
Supports partial scoring (0.0, 0.5, 1.0) based on evidence strength.
"""

import re
import logging

from config import NFR_EVIDENCE_MAP

logger = logging.getLogger(__name__)


def _build_search_corpus(architecture: dict) -> str:
    """
    Build a single lowercase text corpus from all architecture elements
    for efficient keyword scanning.
    """
    parts = []

    # Architecture style itself is evidence
    parts.append(architecture.get("architecture_style", ""))

    # All layer names
    for layer in architecture.get("layers", []):
        parts.append(layer.get("name", ""))

    # All component names and responsibilities
    for comp in architecture.get("components", []):
        parts.append(comp.get("name", ""))
        parts.append(comp.get("responsibility", ""))

    # All interaction types
    for inter in architecture.get("interactions", []):
        parts.append(inter.get("type", ""))

    return " ".join(parts).lower()


def _count_evidence(corpus: str, keywords: list[str]) -> tuple[int, list[str]]:
    """
    Count how many evidence keywords appear in the corpus.

    Returns:
        (match_count, list_of_matched_keywords)
    """
    matched = []
    for keyword in keywords:
        if keyword.lower() in corpus:
            matched.append(keyword)
    return len(matched), matched


def compute_nas(architecture: dict, requirements: dict) -> dict:
    """
    Compute NFR Alignment Score.

    Args:
        architecture: Parsed architecture dict
        requirements: Requirements dict with 'non_functional_requirements'

    Returns:
        {
            "score": float (0.0 - 1.0),
            "alignment_map": { nfr_id: { type, score, evidence } },
            "unaligned": [nfr_ids]
        }
    """
    nfrs = requirements.get("non_functional_requirements", [])

    if not nfrs:
        return {"score": 1.0, "alignment_map": {}, "unaligned": []}

    corpus = _build_search_corpus(architecture)
    alignment_map = {}
    unaligned = []
    total_score = 0.0

    for nfr in nfrs:
        nfr_id = nfr.get("id", "?")
        nfr_type = nfr.get("type", "").lower().strip()
        nfr_target = nfr.get("target", "")

        # Get evidence keywords for this NFR type
        evidence_keywords = NFR_EVIDENCE_MAP.get(nfr_type, [])

        if not evidence_keywords:
            # Unknown NFR type — check if target text appears in architecture
            target_keywords = re.findall(r'[a-z]+', nfr_target.lower())
            target_keywords = [w for w in target_keywords if len(w) > 3]
            evidence_keywords = target_keywords

        # Count evidence
        match_count, matched_keywords = _count_evidence(corpus, evidence_keywords)

        # Score based on evidence strength
        if match_count >= 3:
            nfr_score = 1.0   # Strong evidence
        elif match_count == 2:
            nfr_score = 0.75  # Good evidence
        elif match_count == 1:
            nfr_score = 0.5   # Weak evidence
        else:
            nfr_score = 0.0   # No evidence

        total_score += nfr_score

        alignment_map[nfr_id] = {
            "type": nfr_type,
            "target": nfr_target,
            "score": nfr_score,
            "evidence_found": matched_keywords,
            "evidence_checked": len(evidence_keywords),
        }

        if nfr_score == 0.0:
            unaligned.append(nfr_id)

    final_score = total_score / len(nfrs) if nfrs else 0.0

    logger.info(
        f"NAS: {final_score:.3f} | "
        f"Aligned: {len(nfrs) - len(unaligned)}/{len(nfrs)} | "
        f"Unaligned: {unaligned}"
    )

    return {
        "score": round(final_score, 4),
        "alignment_map": alignment_map,
        "unaligned": unaligned,
    }
