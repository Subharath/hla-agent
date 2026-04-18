"""
HLA Agent — LSCS: Layer Separation Consistency Score

Formula: LSCS = 1 - (layer_violations / total_cross_layer_edges)
"""

import logging
from config import DEFAULT_LAYER_ORDER

logger = logging.getLogger(__name__)


def _get_layer_order(layer_name, architecture):
    for layer in architecture.get("layers", []):
        if layer.get("name", "").lower().strip() == layer_name.lower().strip():
            return layer.get("order", 99)
    return DEFAULT_LAYER_ORDER.get(layer_name.lower().strip(), 99)


def _build_comp_layer_map(architecture):
    mapping = {}
    for comp in architecture.get("components", []):
        name = comp.get("name", "").strip()
        layer = comp.get("layer", "").strip()
        if name:
            mapping[name] = layer
            mapping[name.lower()] = layer
    return mapping


def _detect_violations(architecture, interactions):
    violations = []
    clm = _build_comp_layer_map(architecture)
    style = architecture.get("architecture_style", "").lower()

    # Find gateway components for microservice bypass detection
    gateways = set()
    for c in architecture.get("components", []):
        if any(k in c.get("name", "").lower() for k in ["gateway", "proxy", "router"]):
            gateways.add(c["name"])

    for inter in interactions:
        fc = inter.get("from", "").strip()
        tc = inter.get("to", "").strip()
        fl = clm.get(fc, clm.get(fc.lower(), ""))
        tl = clm.get(tc, clm.get(tc.lower(), ""))
        if not fl or not tl:
            continue

        fo = _get_layer_order(fl, architecture)
        to = _get_layer_order(tl, architecture)

        # Upward dependency violation
        if fo > to:
            violations.append({
                "from": fc, "to": tc,
                "reason": f"Upward dependency: {fc} (L{fo}) -> {tc} (L{to})"
            })

        # Microservice gateway bypass
        if "microservice" in style and fl.lower() in ("presentation", "ui", "frontend", "client"):
            if tc not in gateways and tl.lower() in ("business logic", "business", "service"):
                violations.append({
                    "from": fc, "to": tc,
                    "reason": f"Gateway bypass: {fc} -> {tc}"
                })

    return violations


def compute_lscs(architecture):
    interactions = architecture.get("interactions", [])
    if not interactions:
        return {"score": 1.0, "violations": 0, "total_cross_layer_edges": 0, "violation_details": []}

    clm = _build_comp_layer_map(architecture)
    cross = 0
    for inter in interactions:
        fc = inter.get("from", "").strip()
        tc = inter.get("to", "").strip()
        fl = clm.get(fc, clm.get(fc.lower(), "")).lower()
        tl = clm.get(tc, clm.get(tc.lower(), "")).lower()
        if fl and tl and fl != tl:
            cross += 1

    violations = _detect_violations(architecture, interactions)
    nv = len(violations)
    score = 1.0 - (nv / cross) if cross > 0 else 1.0
    score = max(0.0, min(1.0, score))

    logger.info(f"LSCS: {score:.3f} | Violations: {nv}, Cross-layer: {cross}")
    return {
        "score": round(score, 4),
        "violations": nv,
        "total_cross_layer_edges": cross,
        "violation_details": violations,
    }
