"""
HLA Agent — Prompt Builder
Constructs the 5-layer structured prompt that forces LLMs
to produce valid, parseable architecture JSON output.

Layers:
  1. Role Assignment — establish architect persona
  2. Context Injection — inject all FR/NFR requirements
  3. Output Schema Enforcement — strict JSON template
  4. Constraint Specification — architecture rules
  5. Quality Guardrails — completeness checks
"""

import json
from typing import Optional


def build_architecture_prompt(requirements: dict, feedback: Optional[str] = None) -> str:
    """
    Build the full structured prompt from requirements JSON.

    Args:
        requirements: Dict with 'project', 'functional_requirements', 'non_functional_requirements'
        feedback: Optional feedback string for regeneration loops (e.g., "Improve scalability")

    Returns:
        Complete prompt string ready to send to any LLM
    """
    project_name = requirements.get("project", "Unknown System")
    frs = requirements.get("functional_requirements", [])
    nfrs = requirements.get("non_functional_requirements", [])

    # ── Layer 1: Role Assignment ──────────────────────────
    role_layer = (
        "You are a senior software architect with deep expertise across ALL architectural styles. "
        "You evaluate each project's requirements objectively and select the simplest architecture "
        "that fully satisfies both functional and non-functional requirements. You do NOT have a "
        "preference for any particular style — you choose based solely on the complexity and nature "
        "of the requirements."
    )

    # ── Layer 2: Context Injection ────────────────────────
    fr_text = "\n".join(
        f"  - [{fr['id']}] {fr['description']}" for fr in frs
    )
    nfr_text = "\n".join(
        f"  - [{nfr['id']}] ({nfr['type']}) {nfr['target']}" for nfr in nfrs
    )

    context_layer = (
        f"You are designing a high-level architecture for: **{project_name}**\n\n"
        f"FUNCTIONAL REQUIREMENTS:\n{fr_text}\n\n"
        f"NON-FUNCTIONAL REQUIREMENTS:\n{nfr_text}"
    )

    # ── Layer 3: Output Schema Enforcement ────────────────
    schema_layer = """
OUTPUT FORMAT: You MUST respond with ONLY a valid JSON object. No explanations, no markdown, no code fences.
The JSON MUST follow this EXACT schema:

{
  "architecture_style": "<one of: Layered Architecture, Event-Driven Architecture, Microkernel Architecture, Microservices Architecture, Space-Based Architecture>",
  "layers": [
    {
      "name": "<layer name>",
      "order": <integer, 1 = topmost>
    }
  ],
  "components": [
    {
      "name": "<PascalCase name ending with a role suffix like Service, Controller, Repository, Gateway, Handler, Manager, Engine, etc.>",
      "layer": "<must match one of the layer names above>",
      "responsibility": "<clear sentence of at least 8 words describing what this component does>"
    }
  ],
  "interactions": [
    {
      "from": "<component name (must match a component above)>",
      "to": "<component name (must match a component above)>",
      "type": "<one of: REST, gRPC, Event, Message Queue, Database, WebSocket, Direct Call>",
      "direction": "<one of: down, up, lateral>"
    }
  ]
}
"""

    # ── Layer 4: Constraint Specification ─────────────────
    constraint_layer = """
ARCHITECTURE STYLE SELECTION — evaluate requirements FIRST, then choose:
- **Layered Architecture**: Best for systems with clear separation of concerns, moderate scale, CRUD-heavy workflows. DEFAULT choice unless requirements clearly demand otherwise.
- **Event-Driven Architecture**: Best when requirements emphasize real-time notifications, async workflows, data streaming, or loosely coupled producers/consumers.
- **Microkernel Architecture**: Best for extensible applications, product-based applications needing 3rd party plugins, or systems requiring isolated execution of dynamic rules.
- **Microservices Architecture**: ONLY for systems with multiple independent business domains, teams working independently, or extreme horizontal scaling (>50k concurrent users across distinct services).
- **Space-Based Architecture**: Best for systems requiring extremely high scalability and unpredictable concurrent user volumes, mitigating database bottlenecks via in-memory data grids.

⚠️ DO NOT default to Microservices. For systems with fewer than 5 truly independent domains, prefer Layered or Microkernel. Simpler is better when requirements allow it.

STRUCTURAL CONSTRAINTS — follow these strictly:
1. Choose the SIMPLEST architecture style that fully satisfies ALL requirements.
2. Define at least 3 distinct layers appropriate to your chosen style.
3. Create at least 8 components distributed across layers.
4. Every component name MUST end with a role suffix (Service, Controller, Repository, Gateway, Handler, Manager, Engine, Processor, etc.).
5. Every component MUST have a clear, specific responsibility (at least 8 words).
6. Define interactions that show how components communicate.
7. Interactions should primarily flow DOWNWARD (higher layers call lower layers).
8. Style-specific rules:
   - Layered Architecture: ensure strict layer separation, no skipping layers.
   - Event-Driven Architecture: include a Message Broker or Event Bus component.
   - Microkernel Architecture: include a Core System and separate Plugin modules.
   - Microservices Architecture: include API Gateway and Service Registry components.
   - Space-Based Architecture: include Processing Unit and Virtualized Middleware components.
"""

    # ── Layer 5: Quality Guardrails ───────────────────────
    guardrail_layer = """
QUALITY REQUIREMENTS:
1. EVERY functional requirement must be addressable by at least one component.
2. Non-functional requirements must be reflected in architectural decisions:
   - Scalability → caching, connection pooling, read replicas, stateless design, load balancing, async processing
   - Performance → caching layer, indexing, async processing, lazy loading, compression
   - Security → authentication service, encryption, access control, input validation, audit logging
   - Availability → redundancy, failover, health monitoring, graceful degradation, hot standby
   - Reliability → retry mechanisms, transaction management, idempotent operations, data validation, backup strategies
   - Maintainability → modular design, dependency injection, interface abstractions, repository pattern
3. Components must NOT be generic placeholders. Each must have a specific, meaningful role.
4. Layer boundaries must be respected — no circular dependencies.
5. The architecture must be PRODUCTION-READY, not academic or toy-level.

RESPOND WITH ONLY THE JSON. NO OTHER TEXT.
"""

    # ── Assemble the full prompt ──────────────────────────
    parts = [role_layer, context_layer, schema_layer, constraint_layer, guardrail_layer]

    # ── Regeneration feedback (if applicable) ─────────────
    if feedback:
        feedback_layer = (
            f"\n⚠️ IMPORTANT — PREVIOUS ATTEMPT WAS REJECTED. Address these issues:\n"
            f"{feedback}\n"
            f"Generate an IMPROVED architecture that fixes these specific problems.\n"
        )
        parts.append(feedback_layer)

    return "\n\n".join(parts)


def build_feedback_from_scores(scores: dict, thresholds: dict) -> str:
    """
    Build a targeted feedback string from metric scores that fell below thresholds.

    Args:
        scores: Dict of metric_name → score (e.g., {"RCR": 0.6, "NAS": 0.5, ...})
        thresholds: Dict of metric_name → threshold

    Returns:
        Feedback string describing what to improve
    """
    feedback_lines = []

    metric_advice = {
        "RCR": (
            "REQUIREMENT COVERAGE IS LOW. Ensure EVERY functional requirement is addressed "
            "by at least one component. Add specific service components for uncovered requirements."
        ),
        "NAS": (
            "NFR ALIGNMENT IS WEAK. Add architectural elements that directly support non-functional "
            "requirements: load balancers for scalability, caching for performance, auth services "
            "for security, redundancy for availability."
        ),
        "SMI": (
            "MODULARITY IS POOR. Reduce cross-layer dependencies. Keep components within the same "
            "layer communicating internally. Minimize direct calls between distant layers."
        ),
        "LSCS": (
            "LAYER SEPARATION IS VIOLATED. Ensure interactions flow DOWNWARD only. Lower layers "
            "must NOT call higher layers. Remove any upward dependencies or circular calls."
        ),
        "SCI": (
            "STRUCTURAL CLARITY IS LOW. Use clear naming conventions: every component name must "
            "end with Service, Controller, Repository, Gateway, Handler, etc. Every component "
            "must have a detailed responsibility description (at least 8 words)."
        ),
    }

    for metric, score in scores.items():
        if metric in thresholds and score < thresholds[metric]:
            shortfall = thresholds[metric] - score
            feedback_lines.append(
                f"- {metric} scored {score:.2f} (need ≥ {thresholds[metric]:.2f}, "
                f"shortfall: {shortfall:.2f}). {metric_advice.get(metric, 'Improve this metric.')}"
            )

    if not feedback_lines:
        return ""

    return "\n".join(feedback_lines)
