"""
HLA Agent — NAS: NFR Alignment Score (Deterministic)

Deterministic, auditable scoring engine aligned to ATAM quality concerns.
No LLM is used for validation.

Formula:
        NAS = average(nfr_support_score_i)

Each NFR score is computed from explicit architecture evidence:
    - Component names/responsibilities
    - Interaction protocol types
    - Style compatibility bonuses/penalties
"""

import re
import logging

logger = logging.getLogger(__name__)


STYLE_ALIASES = {
    "layered architecture": "layered",
    "layered": "layered",
    "event-driven architecture": "event-driven",
    "event driven architecture": "event-driven",
    "event-driven": "event-driven",
    "event": "event-driven",
    "microkernel architecture": "microkernel",
    "microkernel": "microkernel",
    "plugin architecture": "microkernel",
    "microservices architecture": "microservices",
    "microservice architecture": "microservices",
    "microservices": "microservices",
    "space-based architecture": "space-based",
    "space based architecture": "space-based",
    "space-based": "space-based",
}


# Implicit indicators: looser, human-phrased cues often used by LLMs that imply
# support for an NFR but are not explicit technology names. These grant partial credit.
IMPLICIT_INDICATORS = {
    "performance": ["low latency", "fast response", "response time", "throughput", "quick responses", "optimize latency"],
    "scalability": ["handle spikes", "scale horizontally", "scale up", "scale out", "elastic", "handle high load", "concurrent users"],
    "availability": ["always available", "99.9", "failover", "no single point of failure", "graceful degradation"],
    "security": ["secure", "access control", "prevent attacks", "input validation", "authentication", "authorization"],
    "maintainability": ["modular", "easy to change", "decouple", "separation of concerns", "testable"],
    "reliability": ["robust", "resilient", "handles failures", "retry logic", "error handling"],
}


EVIDENCE_KEYWORDS = {
    "scalability": {
        "high": ["load balancer", "autoscale", "auto scale", "shard", "partition", "in-memory grid", "virtualized middleware"],
        "medium": ["cache", "queue", "stateless", "replica", "cluster", "horizontal"],
    },
    "performance": {
        "high": ["cache", "redis", "cdn", "index", "in-memory", "read replica"],
        "medium": ["async", "queue", "batch", "connection pool", "pagination", "compress"],
    },
    "security": {
        "high": ["encryption", "tls", "oauth", "jwt", "rbac", "mfa"],
        "medium": ["auth", "token", "audit", "validate", "permission", "access control"],
    },
    "availability": {
        "high": ["failover", "redundant", "high availability", "hot standby", "health check"],
        "medium": ["replica", "retry", "monitoring", "watchdog", "backup", "circuit breaker"],
    },
    "maintainability": {
        "high": ["modular", "plugin", "abstraction", "interface", "dependency injection"],
        "medium": ["adapter", "repository", "separation of concerns", "layered", "port"],
    },
    "reliability": {
        "high": ["idempotent", "transaction", "saga", "dead letter", "rollback"],
        "medium": ["retry", "circuit breaker", "validation", "data integrity", "consistency"],
    },
}


STYLE_QUALITY_BONUS = {
    "microservices": {"scalability": 0.15, "availability": 0.10},
    "event-driven": {"scalability": 0.10, "performance": 0.10, "reliability": 0.05},
    "space-based": {"scalability": 0.20, "performance": 0.15, "availability": 0.05},
    "layered": {"maintainability": 0.15, "security": 0.05},
    "microkernel": {"maintainability": 0.15, "reliability": 0.05},
}


STYLE_QUALITY_PENALTY = {
    "layered": {"scalability": 0.08},
    "microkernel": {"performance": 0.05},
}


INTERACTION_EVIDENCE = {
    "event": {"scalability": 0.10, "performance": 0.05, "reliability": 0.05},
    "message queue": {"scalability": 0.10, "reliability": 0.10},
    "grpc": {"performance": 0.10},
    "websocket": {"performance": 0.05},
    "rest": {"maintainability": 0.05},
}


def _normalize_style(style: str) -> str:
    return STYLE_ALIASES.get((style or "").strip().lower(), "layered")


def _normalize_nfr_type(nfr_type: str) -> str:
    base = (nfr_type or "").strip().lower()
    if base in EVIDENCE_KEYWORDS:
        return base
    if base in {"secure", "security"}:
        return "security"
    if base in {"speed", "latency", "throughput"}:
        return "performance"
    return base


def _build_architecture_text(architecture: dict) -> str:
    parts = []
    for comp in architecture.get("components", []):
        parts.append(comp.get("name", ""))
        parts.append(comp.get("responsibility", ""))
    for inter in architecture.get("interactions", []):
        parts.append(inter.get("type", ""))
    return " ".join(parts).lower()


def _keyword_hits(text: str, keywords: list[str]) -> int:
    hits = 0
    for kw in keywords:
        # exact whole-word match
        if re.search(r"\b" + re.escape(kw.lower()) + r"\b", text):
            hits += 1
        else:
            # loose substring match for multiword keywords
            if kw.lower() in text:
                hits += 1
    return hits


def _implicit_hits(text: str, indicators: list[str]) -> int:
    hits = 0
    for phrase in indicators:
        if phrase.lower() in text:
            hits += 1
    return hits


def _score_nfr(architecture: dict, nfr: dict, style: str) -> tuple[float, str]:
    nfr_type = _normalize_nfr_type(nfr.get("type", ""))
    if nfr_type not in EVIDENCE_KEYWORDS:
        return 0.5, "Unknown NFR type; assigned neutral deterministic baseline (0.5)."

    arch_text = _build_architecture_text(architecture)
    evidence = EVIDENCE_KEYWORDS[nfr_type]

    high_hits = _keyword_hits(arch_text, evidence["high"])
    med_hits = _keyword_hits(arch_text, evidence["medium"])
    implicit_hits = _implicit_hits(arch_text, IMPLICIT_INDICATORS.get(nfr_type, []))

    # Deterministic evidence score from explicit mechanisms + implicit indicators
    evidence_score = min(1.0, (0.30 * high_hits) + (0.12 * med_hits) + (0.06 * implicit_hits))

    # Interaction-level protocol support
    interaction_bonus = 0.0
    for inter in architecture.get("interactions", []):
        itype = (inter.get("type", "") or "").strip().lower()
        interaction_bonus += INTERACTION_EVIDENCE.get(itype, {}).get(nfr_type, 0.0)
    interaction_bonus = min(0.20, interaction_bonus)

    style_bonus = STYLE_QUALITY_BONUS.get(style, {}).get(nfr_type, 0.0)
    style_penalty = STYLE_QUALITY_PENALTY.get(style, {}).get(nfr_type, 0.0)

    score = max(0.0, min(1.0, evidence_score + interaction_bonus + style_bonus - style_penalty))
    reasoning = (
        f"type={nfr_type}, high_hits={high_hits}, medium_hits={med_hits}, implicit_hits={implicit_hits}, "
        f"interaction_bonus={interaction_bonus:.2f}, style={style}, "
        f"style_bonus={style_bonus:.2f}, style_penalty={style_penalty:.2f}"
    )
    return score, reasoning


def compute_nas(architecture: dict, requirements: dict, evaluator_model: str = None) -> dict:
    """
    Compute NFR Alignment Score using deterministic evidence rules.

    Args:
        architecture: Parsed architecture dict
        requirements: Requirements dict with 'non_functional_requirements'
        evaluator_model: Kept for backward compatibility. Ignored.

    Returns:
        {
            "score": float (0.0 - 1.0),
            "aligned_count": int,
            "alignment_map": { nfr_id: { type, score, reasoning } },
            "unaligned": [nfr_ids]
        }
    """
    nfrs = requirements.get("non_functional_requirements", [])

    if not nfrs:
        return {"score": 1.0, "alignment_map": {}, "unaligned": []}

    alignment_map = {}
    unaligned = []
    total_score = 0.0
    aligned_count = 0

    style = _normalize_style(architecture.get("architecture_style", ""))
    logger.info("Evaluating NAS using deterministic rules engine")

    for nfr in nfrs:
        nfr_id = nfr.get("id")
        nfr_type = nfr.get("type", "")
        nfr_target = nfr.get("target", "")

        score, reasoning = _score_nfr(architecture, nfr, style)
        total_score += score

        alignment_map[nfr_id] = {
            "type": nfr_type,
            "target": nfr_target,
            "score": round(score, 4),
            "coverage": 1 if score >= 0.5 else 0,
            "aligned": score >= 0.5,
            "reasoning": reasoning,
        }

        if score < 0.5:
            unaligned.append(nfr_id)
        else:
            aligned_count += 1

    final_score = total_score / len(nfrs) if nfrs else 0.0

    logger.info(
        f"NAS: {final_score:.3f} | Aligned: {len(nfrs) - len(unaligned)}/{len(nfrs)} | Unaligned: {unaligned}"
    )

    return {
        "score": round(final_score, 4),
        "aligned_count": aligned_count,
        "alignment_map": alignment_map,
        "unaligned": unaligned,
    }
