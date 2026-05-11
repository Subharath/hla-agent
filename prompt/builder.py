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


def build_architecture_prompt(requirements: dict, feedback: Optional[str] = None, candidate_num: int = 1) -> str:
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

    # ── Layer 1: Role Assignment & NFR Prioritization ────────
    # Common architecture review practice: to explore tradeoffs, ask for candidates
    # optimized for different quality attributes (NFR lenses).
    if candidate_num == 1:
        priority_lens = "OPTIMIZE FOR SIMPLICITY: Your primary goal is to find the most balanced, maintainable, and simple architecture that meets the baseline requirements without over-engineering."
    else:
        priority_lens = "OPTIMIZE FOR SCALE & DECOUPLING: Your primary goal is to maximize scalability, performance, and independent deployability, prioritizing distributed patterns even if it introduces complexity."

    role_layer = (
        "You are a senior software architect with deep expertise across ALL architectural styles. "
        "You evaluate each project's requirements objectively. "
        f"For this specific candidate generation, {priority_lens} "
        "You do NOT have a preference for any particular style — you choose based on the requirements and your assigned optimization goal."
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
  "pros_and_cons": "<2-3 sentence expert explanation of why this architecture is a good or bad fit for this SPECIFIC scenario, outlining its ATAM tradeoffs>",
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
Use ONLY the canonical style options from Software Architecture Patterns, 2nd Edition (Mark Richards):
Layered, Event-Driven, Microkernel, Microservices, Space-Based.
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

    # Explicit NFR evidence guidance — ensure the LLM includes auditable mappings
    # in component responsibilities so deterministic NAS can find explicit traces.
    # NOTE: This MUST remain a free-text instruction (output still strictly JSON).
    explicit_nfr_instruction = (
        "\nEXPLICIT NFR MAPPING REQUIREMENT:\n"
        "For EVERY non-functional requirement above, include an explicit hint inside at least one component's 'responsibility'. "
        "Use a short phrase such as 'Supports NFR [NFR_ID] via <mechanism>' or 'Handles [NFR_ID]: <mechanism>'. "
        "Examples: 'Supports NFR NFR1 via Redis cache', 'Handles NFR NFR3: OAuth gateway + TLS'. "
        "This makes NFR-handling auditable and machine-detectable for evaluation.\n"
    )
    parts = [role_layer, context_layer, schema_layer, constraint_layer, guardrail_layer, explicit_nfr_instruction]

    # ── Assemble the full prompt ──────────────────────────

    # ── Regeneration feedback (if applicable) ─────────────
    if feedback:
        feedback_layer = (
            f"\n⚠️ IMPORTANT — PREVIOUS ATTEMPT WAS REJECTED. Address these issues:\n"
            f"{feedback}\n"
            f"Generate an IMPROVED architecture that fixes these specific problems.\n"
        )
        parts.append(feedback_layer)

    return "\n\n".join(parts)


def build_diagram_prompt(
    *,
    architecture: dict,
    requirements: dict,
    diagram_kind: str,
    title: str,
    iteration: int,
    previous_diagram: Optional[str] = None,
    previous_diagram_cas: Optional[float] = None,
    feedback_issues: Optional[list[str]] = None,
    user_feedback: Optional[str] = None,
    reference_diagram: Optional[str] = None,
) -> str:
    """Build a diagram-generation prompt for either Mermaid or PlantUML.

    Constraints:
    - Output must be ONLY the diagram source (no markdown, no code fences).
    - Must align diagram structure/layout to the selected architecture style.
    - Iteration 2 is an explicit improvement pass using deterministic feedback.
    """

    project_name = requirements.get("project", "System")
    style = architecture.get("architecture_style", "Architecture")
    layers = architecture.get("layers", []) or []
    components = architecture.get("components", []) or []
    interactions = architecture.get("interactions", []) or []

    def safe_id(s: str) -> str:
        return (s or "").strip().replace(" ", "_").replace("-", "_")

    layer_lines = []
    for l in layers:
        name = (l.get("name", "") or "").strip()
        order = l.get("order", "")
        if name:
            layer_lines.append(f"- L{order}: {name}")

    comp_lines = []
    for c in components:
        name = (c.get("name", "") or "").strip()
        layer = (c.get("layer", "") or "").strip()
        resp = (c.get("responsibility", "") or "").strip()
        if name:
            resp_short = (resp[:120] + "…") if len(resp) > 120 else resp
            comp_lines.append(f"- {name} (layer={layer}, id={safe_id(name)}): {resp_short}")

    inter_lines = []
    for i in interactions:
        f = (i.get("from", "") or "").strip()
        t = (i.get("to", "") or "").strip()
        typ = (i.get("type", "") or "").strip()
        direction = (i.get("direction", "") or "").strip()
        if f and t:
            inter_lines.append(f"- {f} -> {t} (type={typ}, direction={direction})")

    # Common role/context
    role = (
        "You are a principal software architect and UML/diagramming specialist. "
        "You produce clear, industry-standard architecture diagrams for engineering and audit stakeholders."
    )

    context = (
        f"PROJECT: {project_name}\n"
        f"TITLE: {title}\n"
        f"ARCHITECTURE STYLE (MUST ALIGN TO THIS): {style}\n\n"
        f"LAYERS:\n" + ("\n".join(layer_lines) if layer_lines else "- (none)") + "\n\n"
        f"COMPONENTS (authoritative list):\n" + ("\n".join(comp_lines) if comp_lines else "- (none)") + "\n\n"
        f"INTERACTIONS (authoritative list):\n" + ("\n".join(inter_lines) if inter_lines else "- (none)")
    )

    if reference_diagram:
        context += (
            "\n\nREFERENCE DIAGRAM (approved / must stay consistent):\n"
            + (reference_diagram.strip() + "\n")
        )

    # Style-alignment rules to make the diagram explicitly match the selected style.
    style_rules = (
        "STYLE-SPECIFIC DIAGRAM ALIGNMENT RULES:\n"
        "- Layered Architecture: group components by layer and keep dependencies mostly downward between adjacent layers.\n"
        "- Microservices Architecture: show an explicit API Gateway entry point and a Service Registry/Discovery; isolate services as separate groups/packages.\n"
        "- Event-Driven Architecture: show an explicit Event Bus/Broker; producers/consumers should connect via the broker (avoid direct service-to-service for events).\n"
        "- Microkernel Architecture: show a Core/Kernel and separate Plugin/Extension modules; plugins depend on the core.\n"
        "- Space-Based Architecture: show Processing Units and a shared Data Grid/Virtualized Middleware; discourage direct DB coupling in the main flow.\n"
    )

    if diagram_kind not in {"mermaid", "plantuml"}:
        raise ValueError(f"Unsupported diagram_kind: {diagram_kind}")

    if diagram_kind == "mermaid":
        schema = (
            "OUTPUT FORMAT (Mermaid):\n"
            "- Output ONLY valid Mermaid source. No markdown. No code fences.\n"
            "- Use: flowchart TD (or LR).\n"
            "- Use subgraph blocks for layers when layers exist.\n"
            "- Use the provided component ids exactly as listed (id=...).\n"
            "- Draw arrows for ALL interactions; label arrows with the interaction type.\n"
            "- Keep it simple and readable for a GitHub README.\n"
        )

    else:
        schema = (
            "OUTPUT FORMAT (PlantUML Component Diagram):\n"
            "- Output ONLY valid PlantUML. No markdown. No code fences.\n"
            "- MUST include @startuml and @enduml.\n"
            "- MUST include: skinparam componentStyle rectangle\n"
            "- Use package blocks for layers (or service boundaries), and place components inside.\n"
            "- Declare components using: [ComponentName] as ComponentId (where ComponentId is the provided id=...).\n"
            "- Add dependency arrows for ALL interactions; label arrows with the interaction type (REST/gRPC/Event/etc.).\n"
            "- Prefer an industry-standard component diagram style (clear boundaries, consistent naming, minimal clutter).\n"
        )

    improvement = ""
    if iteration >= 2:
        issues_txt = "\n".join(f"- {x}" for x in (feedback_issues or [])) or "- (no issues provided)"
        prev_score_txt = f"{previous_diagram_cas:.4f}" if previous_diagram_cas is not None else "(not provided)"
        extra_user_feedback = (user_feedback or "").strip()
        user_feedback_block = f"\nUSER NOTES:\n{extra_user_feedback}\n" if extra_user_feedback else ""
        improvement = (
            "\nITERATION 2 (IMPROVEMENT PASS):\n"
            f"- Previous Diagram_CAS: {prev_score_txt}\n"
            "- You MUST improve the diagram by fixing the issues below while keeping it valid.\n"
            "- Do not remove correct content; prefer adding missing components/interactions and adding missing style structure.\n"
            "- Even if the issue list looks small, do a strict compliance pass: ensure EVERY interaction is present and labeled, and the diagram structure clearly reflects the selected architecture style.\n"
            "ISSUES TO FIX:\n"
            f"{issues_txt}\n\n"
            f"{user_feedback_block}\n"
            "PREVIOUS DIAGRAM (for editing):\n"
            f"{previous_diagram or ''}\n"
        )

    return "\n\n".join([role, context, style_rules, schema, improvement]).strip() + "\n"


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
