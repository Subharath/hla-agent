"""
HLA Agent — LSCS: Logical Structure Consistency Score
(Formerly Layer Separation Consistency Score)

Style-Aware Topological Consistency:
- Layered: Enforces strict downward dependency (no sinkholes/upward calls).
- Microservices: Enforces Gateway usage and penalizes tight cyclic dependencies.
- Event-Driven: Enforces broker mediation (producers don't call consumers directly).
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


def _detect_layered_violations(architecture, interactions, clm):
    """Detect upward dependencies or layer bypassing in Layered style."""
    violations = []
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
    return violations


def _detect_microservice_violations(architecture, interactions, clm):
    """Detect gateway bypass and point-to-point cyclic coupling in Microservices."""
    violations = []
    gateways = set()
    for c in architecture.get("components", []):
        if any(k in c.get("name", "").lower() for k in ["gateway", "proxy", "router"]):
            gateways.add(c["name"])

    # Build adjacency list for cycle detection
    adj = {}
    for inter in interactions:
        fc = inter.get("from", "").strip()
        tc = inter.get("to", "").strip()
        adj.setdefault(fc, []).append(tc)

        # Check Gateway bypass
        fl = clm.get(fc, clm.get(fc.lower(), ""))
        tl = clm.get(tc, clm.get(tc.lower(), ""))
        if fl.lower() in ("presentation", "ui", "frontend", "client"):
            if tc not in gateways and gateways:
                violations.append({
                    "from": fc, "to": tc,
                    "reason": f"Gateway bypass: UI directly calls internal service {tc}"
                })

    # Simple length-2 cycle detection (A -> B and B -> A)
    for u in adj:
        for v in adj[u]:
            if u in adj.get(v, []):
                violations.append({
                    "from": u, "to": v,
                    "reason": f"Cyclic dependency detected between {u} and {v}"
                })

    # Remove duplicates from cycle detection
    return [dict(t) for t in {tuple(d.items()) for d in violations}]


def _detect_event_driven_violations(architecture, interactions):
    """Detect direct point-to-point calls bypassing brokers in Event-Driven."""
    violations = []
    brokers = set()
    for c in architecture.get("components", []):
        if any(k in c.get("name", "").lower() for k in ["bus", "broker", "queue", "topic", "kafka", "rabbitmq"]):
            brokers.add(c["name"])

    # If no brokers are defined but it's event-driven, that's a massive violation
    if not brokers:
        violations.append({
            "from": "System", "to": "System",
            "reason": "Event-Driven architecture missing an Event Broker/Bus"
        })
        return violations

    for inter in interactions:
        fc = inter.get("from", "").strip()
        tc = inter.get("to", "").strip()
        
        # A direct call between non-broker services might be a violation
        # We allow UI -> Gateway, but Service -> Service should usually go through Broker
        # This is a heuristic.
        is_fc_broker = fc in brokers or any(b in fc.lower() for b in ["bus", "broker", "queue"])
        is_tc_broker = tc in brokers or any(b in tc.lower() for b in ["bus", "broker", "queue"])
        is_fc_ui = any(k in fc.lower() for k in ["ui", "client", "frontend", "gateway"])

        if not is_fc_broker and not is_tc_broker and not is_fc_ui:
             violations.append({
                "from": fc, "to": tc,
                "reason": f"Direct point-to-point coupling: {fc} -> {tc} (bypasses broker)"
            })
    return violations


def compute_lscs(architecture):
    interactions = architecture.get("interactions", [])
    if not interactions:
        return {"score": 1.0, "violations": 0, "total_edges": 0, "violation_details": []}

    clm = _build_comp_layer_map(architecture)
    style = architecture.get("architecture_style", "").lower()

    if "microservice" in style:
        violations = _detect_microservice_violations(architecture, interactions, clm)
    elif "event" in style:
        violations = _detect_event_driven_violations(architecture, interactions)
    else:
        # Default to Layered structural rules
        violations = _detect_layered_violations(architecture, interactions, clm)

    nv = len(violations)
    total_edges = len(interactions)
    score = 1.0 - (nv / total_edges) if total_edges > 0 else 1.0
    score = max(0.0, min(1.0, score))

    logger.info(f"LSCS: {score:.3f} | Style: {style} | Violations: {nv}, Total Edges: {total_edges}")
    return {
        "score": round(score, 4),
        "violations": nv,
        "total_edges": total_edges,
        "violation_details": violations,
    }
