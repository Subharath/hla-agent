"""
HLA Agent — LSCS: Logical Structure Consistency Score
(Formerly Layer Separation Consistency Score)

Style-Aware Topological Consistency:
- Layered: Enforces strict downward dependency (no sinkholes/upward calls).
- Microservices: Enforces Gateway usage and penalizes tight cyclic dependencies.
- Event-Driven: Enforces broker mediation (producers don't call consumers directly).
- Microkernel: Enforces Core/Plugin separation and plugin isolation.
- Space-Based: Enforces processing-unit mediation and discourages direct datastore coupling.
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
    """Detect microservice-specific structural issues.

    Microservices LSCS should be more specific than generic layer checks:
    - require API Gateway / edge entry point
    - require Service Registry / discovery support
    - flag frontend/client calls that bypass the gateway
    - flag tight cyclic coupling between service components
    """
    violations = []

    comps = architecture.get("components", [])
    component_names = {c.get("name", "").strip() for c in comps if c.get("name", "").strip()}
    lower_names = {name.lower() for name in component_names}

    gateway_names = {
        name for name in component_names
        if any(k in name.lower() for k in ["api gateway", "gateway", "edge", "proxy", "router"])
    }
    registry_names = {
        name for name in component_names
        if any(k in name.lower() for k in ["service registry", "registry", "discovery", "eureka", "consul"])
    }

    if not gateway_names:
        violations.append({
            "from": "System", "to": "System",
            "reason": "Microservices architecture missing API Gateway / edge entry point"
        })

    if not registry_names:
        violations.append({
            "from": "System", "to": "System",
            "reason": "Microservices architecture missing Service Registry / discovery support"
        })

    def is_client_like(layer_name: str, component_name: str) -> bool:
        layer_name = (layer_name or "").lower()
        component_name = (component_name or "").lower()
        return any(k in layer_name for k in ["presentation", "ui", "frontend", "client"]) or any(
            k in component_name for k in ["ui", "frontend", "client", "web app", "webapp"]
        )

    def is_gateway_like(component_name: str) -> bool:
        component_name = (component_name or "").lower()
        return any(k in component_name for k in ["api gateway", "gateway", "edge", "proxy", "router"])

    def is_service_like(component_name: str) -> bool:
        component_name = (component_name or "").lower()
        return component_name.endswith("service") or "service " in component_name or " service" in component_name

    # Build adjacency list for cycle detection
    adj = {}
    for inter in interactions:
        fc = inter.get("from", "").strip()
        tc = inter.get("to", "").strip()
        adj.setdefault(fc, []).append(tc)

        # Check gateway bypass from client-facing entry points to internal services.
        fl = clm.get(fc, clm.get(fc.lower(), ""))
        tl = clm.get(tc, clm.get(tc.lower(), ""))
        if is_client_like(fl, fc):
            if not is_gateway_like(tc) and gateway_names:
                violations.append({
                    "from": fc, "to": tc,
                    "reason": f"Gateway bypass: client-facing component {fc} directly calls internal service {tc}"
                })

    # Simple length-2 cycle detection only for service-like components.
    for u in adj:
        for v in adj[u]:
            if u in adj.get(v, []) and is_service_like(u) and is_service_like(v):
                violations.append({
                    "from": u, "to": v,
                    "reason": f"Cyclic service coupling detected between {u} and {v}"
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


def _detect_microkernel_violations(architecture, interactions):
    """Detect microkernel anti-patterns: plugin isolation breaks and missing core/kernel."""
    violations = []
    comps = architecture.get("components", [])

    core_components = {
        c.get("name", "") for c in comps
        if any(k in c.get("name", "").lower() for k in ["core", "kernel"])
    }
    plugin_components = {
        c.get("name", "") for c in comps
        if any(k in c.get("name", "").lower() for k in ["plugin", "extension", "module"])
    }

    if not core_components:
        violations.append({
            "from": "System", "to": "System",
            "reason": "Microkernel architecture missing Core/Kernel component"
        })

    for inter in interactions:
        fc = inter.get("from", "").strip()
        tc = inter.get("to", "").strip()

        if fc in plugin_components and tc in plugin_components:
            violations.append({
                "from": fc, "to": tc,
                "reason": f"Plugin-to-plugin coupling: {fc} -> {tc} (should prefer core mediation)"
            })

    return violations


def _detect_space_based_violations(architecture, interactions):
    """Detect space-based anti-patterns: missing processing units or direct DB-heavy service coupling."""
    violations = []
    comps = architecture.get("components", [])

    processing_units = {
        c.get("name", "") for c in comps
        if any(k in c.get("name", "").lower() for k in ["processing unit", "processor", "pu"])
    }
    data_grid = {
        c.get("name", "") for c in comps
        if any(k in c.get("name", "").lower() for k in ["grid", "cache", "space", "middleware"])
    }

    if not processing_units:
        violations.append({
            "from": "System", "to": "System",
            "reason": "Space-Based architecture missing Processing Unit component"
        })

    if not data_grid:
        violations.append({
            "from": "System", "to": "System",
            "reason": "Space-Based architecture missing in-memory grid/virtualized middleware"
        })

    for inter in interactions:
        fc = inter.get("from", "").strip().lower()
        tc = inter.get("to", "").strip().lower()
        db_like = any(k in tc for k in ["database", "sql", "repository"]) or any(k in fc for k in ["database", "sql", "repository"])
        if db_like:
            violations.append({
                "from": inter.get("from", ""),
                "to": inter.get("to", ""),
                "reason": "Direct datastore-oriented coupling is discouraged in Space-Based style"
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
    elif "microkernel" in style or "plugin" in style:
        violations = _detect_microkernel_violations(architecture, interactions)
    elif "space" in style:
        violations = _detect_space_based_violations(architecture, interactions)
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
