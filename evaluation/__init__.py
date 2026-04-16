"""
HLA Agent — Evaluation Engine
Exports the main evaluate_architecture() function and all individual metrics.
"""

from evaluation.rcr import compute_rcr
from evaluation.nas import compute_nas
from evaluation.smi import compute_smi
from evaluation.lscs import compute_lscs
from evaluation.sci import compute_sci
from evaluation.cas import compute_cas, rank_candidates


def evaluate_architecture(architecture: dict, requirements: dict) -> dict:
    """
    Run all 5 metrics on a single architecture candidate.

    Args:
        architecture: Parsed & normalized architecture dict
        requirements: Original requirements dict (FR/NFR)

    Returns:
        Dict with individual scores and CAS:
        {
            "RCR": float, "NAS": float, "SMI": float,
            "LSCS": float, "SCI": float, "CAS": float,
            "details": { per-metric details }
        }
    """
    rcr_result = compute_rcr(architecture, requirements)
    nas_result = compute_nas(architecture, requirements)
    smi_result = compute_smi(architecture)
    lscs_result = compute_lscs(architecture)
    sci_result = compute_sci(architecture)

    scores = {
        "RCR": rcr_result["score"],
        "NAS": nas_result["score"],
        "SMI": smi_result["score"],
        "LSCS": lscs_result["score"],
        "SCI": sci_result["score"],
    }

    cas_result = compute_cas(scores)

    return {
        **scores,
        "CAS": cas_result["cas"],
        "verdict": cas_result["verdict"],
        "details": {
            "rcr": rcr_result,
            "nas": nas_result,
            "smi": smi_result,
            "lscs": lscs_result,
            "sci": sci_result,
            "cas": cas_result,
        },
    }


__all__ = [
    "evaluate_architecture",
    "compute_rcr",
    "compute_nas",
    "compute_smi",
    "compute_lscs",
    "compute_sci",
    "compute_cas",
    "rank_candidates",
]
