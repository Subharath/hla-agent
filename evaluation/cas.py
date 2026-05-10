"""
HLA Agent — CAS: Composite Architecture Score + Ranker

CAS = 0.25*RCR + 0.25*NAS + 0.20*SMI + 0.15*LSCS + 0.15*SCI

Provides:
  - CAS computation from individual scores
  - Verdict classification (Accepted / Marginal / Poor)
  - Candidate ranking across all models
"""

import logging
from config import PHASE1_WEIGHTS, PHASE2_WEIGHTS, CAS_ACCEPTED, CAS_MARGINAL, THRESHOLDS

logger = logging.getLogger(__name__)


def compute_cas(scores: dict, phase: int = 1) -> dict:
    """
    Compute Composite Architecture Score from individual metric scores.

    Args:
        scores: Dict with metric keys
        phase: 1 for Tradeoff Analysis (RCR, NAS), 2 for Structural (SMI, LSCS, SCI)

    Returns:
        {
            "cas": float,
            "verdict": "Accepted" | "Marginal" | "Poor",
            "weighted_breakdown": { metric: weighted_value },
            "below_threshold": [metric_names]
        }
    """
    weighted = {}
    cas = 0.0
    
    weights = PHASE1_WEIGHTS if phase == 1 else PHASE2_WEIGHTS

    for metric, weight in weights.items():
        value = scores.get(metric, 0.0)
        w_value = value * weight
        weighted[metric] = round(w_value, 4)
        cas += w_value

    cas = round(cas, 4)

    verdict = "Accepted"
    if phase == 1:
        if cas >= CAS_ACCEPTED:
            verdict = "Accepted"
        elif cas >= CAS_MARGINAL:
            verdict = "Marginal"
        else:
            verdict = "Poor"
    else:
        verdict = "Structural Evaluation Complete"

    below = [m for m, s in scores.items() if m in THRESHOLDS and s < THRESHOLDS[m]]

    logger.info(f"Phase {phase} CAS: {cas:.4f} → {verdict} | Below threshold: {below}")

    return {
        "cas": cas,
        "verdict": verdict,
        "weighted_breakdown": weighted,
        "below_threshold": below,
    }


def rank_candidates(candidates: list[dict]) -> list[dict]:
    """
    Rank architecture candidates by CAS score (descending).

    Args:
        candidates: List of dicts, each with at least:
            { "model", "candidate_num", "scores": { RCR, NAS, SMI, LSCS, SCI, CAS } }

    Returns:
        Same list sorted by CAS descending, with 'rank' field added (1-based)
    """
    sorted_candidates = sorted(
        candidates,
        key=lambda c: c.get("scores", {}).get("CAS", 0),
        reverse=True,
    )

    for i, candidate in enumerate(sorted_candidates):
        candidate["rank"] = i + 1

    if sorted_candidates:
        winner = sorted_candidates[0]
        logger.info(
            f"Winner: {winner.get('model', '?')} candidate "
            f"{winner.get('candidate_num', '?')} with CAS={winner['scores']['CAS']:.4f}"
        )

    return sorted_candidates
