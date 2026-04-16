"""
HLA Agent — RCR: Requirement Coverage Ratio

Formula: RCR = covered_FRs / total_FRs

For each FR, tokenize the description and check if any component's
name or responsibility contains matching keywords.
A match means the FR is "covered" by the architecture.
"""

import re
import logging

logger = logging.getLogger(__name__)

# Words to ignore during keyword matching (too generic)
STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "can", "could", "should", "would", "will", "may", "might",
    "and", "or", "but", "not", "for", "with", "from", "to", "in",
    "on", "at", "by", "of", "it", "its", "this", "that", "these",
    "those", "has", "have", "had", "do", "does", "did", "get",
    "set", "all", "each", "every", "any", "some", "no", "into",
    "must", "shall", "via", "as", "so", "if", "then", "also",
    "their", "them", "they", "he", "she", "his", "her", "our",
    "your", "my", "we", "us", "me", "him", "i", "you",
}

# Domain-specific synonym mappings for better matching
SYNONYMS = {
    "order": ["order", "purchase", "checkout", "buy", "cart"],
    "payment": ["payment", "pay", "billing", "charge", "transaction", "invoice"],
    "delivery": ["delivery", "deliver", "shipping", "shipment", "dispatch", "courier"],
    "track": ["track", "tracking", "monitor", "trace", "status", "real-time"],
    "manage": ["manage", "management", "admin", "crud", "maintain", "configure"],
    "user": ["user", "customer", "client", "account", "profile", "member"],
    "notification": ["notification", "notify", "alert", "email", "sms", "reminder", "push"],
    "restaurant": ["restaurant", "vendor", "seller", "merchant", "shop", "store"],
    "menu": ["menu", "catalog", "product", "item", "listing", "inventory"],
    "review": ["review", "rating", "rate", "feedback", "comment"],
    "search": ["search", "browse", "find", "filter", "query", "discover"],
    "driver": ["driver", "courier", "rider", "fleet", "dispatch"],
    "schedule": ["schedule", "appointment", "booking", "book", "reservation", "slot"],
    "doctor": ["doctor", "physician", "medical", "health", "clinical", "consultation"],
    "patient": ["patient", "medical record", "health record", "prescription"],
    "task": ["task", "todo", "work item", "ticket", "issue", "backlog"],
    "project": ["project", "workspace", "board", "sprint", "milestone"],
    "assign": ["assign", "assignment", "delegate", "allocate"],
    "report": ["report", "analytics", "statistics", "dashboard", "insight"],
}


def _tokenize(text: str) -> set[str]:
    """Extract meaningful keywords from text, filtering stop words."""
    words = re.findall(r'[a-z]+', text.lower())
    return {w for w in words if w not in STOP_WORDS and len(w) > 2}


def _expand_keywords(keywords: set[str]) -> set[str]:
    """Expand keywords using synonym mappings."""
    expanded = set(keywords)
    for word in keywords:
        for key, synonyms in SYNONYMS.items():
            if word in synonyms:
                expanded.update(synonyms)
    return expanded


def compute_rcr(architecture: dict, requirements: dict) -> dict:
    """
    Compute Requirement Coverage Ratio.

    Args:
        architecture: Parsed architecture dict with 'components'
        requirements: Requirements dict with 'functional_requirements'

    Returns:
        {
            "score": float (0.0 - 1.0),
            "covered": int,
            "total": int,
            "coverage_map": { fr_id: [matching_components] },
            "uncovered": [fr_ids]
        }
    """
    frs = requirements.get("functional_requirements", [])
    components = architecture.get("components", [])

    if not frs:
        return {"score": 1.0, "covered": 0, "total": 0,
                "coverage_map": {}, "uncovered": []}

    # Build component search text (name + responsibility)
    component_texts = []
    for comp in components:
        text = f"{comp.get('name', '')} {comp.get('responsibility', '')}".lower()
        component_texts.append((comp.get("name", ""), text))

    coverage_map = {}
    uncovered = []

    for fr in frs:
        fr_id = fr.get("id", "?")
        fr_desc = fr.get("description", "")

        # Tokenize and expand FR keywords
        fr_keywords = _tokenize(fr_desc)
        fr_keywords_expanded = _expand_keywords(fr_keywords)

        matching_components = []

        for comp_name, comp_text in component_texts:
            comp_keywords = _tokenize(comp_text)

            # Check for overlap between FR keywords and component keywords
            overlap = fr_keywords_expanded & comp_keywords
            if len(overlap) >= 1:  # At least 1 meaningful keyword match
                matching_components.append(comp_name)

        if matching_components:
            coverage_map[fr_id] = matching_components
        else:
            uncovered.append(fr_id)

    covered = len(coverage_map)
    total = len(frs)
    score = covered / total if total > 0 else 0.0

    logger.info(f"RCR: {covered}/{total} = {score:.3f} | Uncovered: {uncovered}")

    return {
        "score": round(score, 4),
        "covered": covered,
        "total": total,
        "coverage_map": coverage_map,
        "uncovered": uncovered,
    }
