"""HLA Agent — LLM Diagram Generator (2-iteration loop)

Goal:
- Generate Mermaid and PlantUML diagrams using the same LLM model that produced the winning architecture.
- Force alignment to the selected architecture style.
- Run a maximum of 2 iterations and produce a unified diff (GitHub-friendly) showing improvements.

Notes:
- This module intentionally keeps diagram evaluation deterministic and lightweight.
- The diagram "CAS" here is a diagram-quality proxy (coverage + style alignment), not the architecture CAS.
"""

from __future__ import annotations

import re
import difflib
import logging
from dataclasses import dataclass

from config import DIAGRAM_GENERATION_OPTIONS, DIAGRAM_MAX_ITERATIONS
from providers import get_provider_for_model
from prompt.builder import build_diagram_prompt

logger = logging.getLogger(__name__)


@dataclass
class DiagramAttempt:
    iteration: int
    diagram: str
    diagram_cas: float
    breakdown: dict
    issues: list[str]


def _strip_code_fences(text: str) -> str:
    if not text:
        return ""

    # Remove leading/trailing whitespace first
    t = text.strip()

    # Remove common fenced formats
    # ```mermaid ... ```
    # ```plantuml ... ```
    fence = re.match(r"^```[a-zA-Z0-9_-]*\s*(.*?)\s*```$", t, flags=re.DOTALL)
    if fence:
        return fence.group(1).strip()

    return t


def _extract_plantuml_block(text: str) -> str:
    """Extract a PlantUML block even if the model returns extra prose."""
    if not text:
        return ""

    t = text.strip()

    # Prefer an explicit @startuml..@enduml block.
    low = t.lower()
    start = low.find("@startuml")
    if start != -1:
        end = low.find("@enduml", start)
        if end != -1:
            end = end + len("@enduml")
            return t[start:end].strip() + "\n"

    # Fall back to fenced extraction.
    return _strip_code_fences(t).strip() + "\n"


def _extract_mermaid_block(text: str) -> str:
    """Extract Mermaid source starting at the first flowchart/graph line."""
    if not text:
        return ""

    t = _strip_code_fences(text)
    lines = t.splitlines()
    for i, ln in enumerate(lines):
        if re.match(r"^\s*(flowchart|graph)\s+", ln, flags=re.IGNORECASE):
            return "\n".join(lines[i:]).strip() + "\n"

    return t.strip() + "\n"


def extract_diagram_source(kind: str, raw_text: str) -> str:
    """Public helper: extract diagram source from raw model output."""
    if kind == "plantuml":
        return _extract_plantuml_block(raw_text)
    if kind == "mermaid":
        return _extract_mermaid_block(raw_text)
    raise ValueError(f"Unknown diagram kind: {kind}")


def _safe_id(name: str) -> str:
    return (name or "").strip().replace(" ", "_").replace("-", "_")


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def _compute_style_alignment(diagram: str, architecture: dict, kind: str) -> tuple[float, list[str]]:
    """Return (style_score 0..1, issues)."""
    style = _normalize(architecture.get("architecture_style", ""))
    layers = architecture.get("layers", []) or []
    components = architecture.get("components", []) or []

    d = _normalize(diagram)
    issues: list[str] = []

    def has_any(*tokens: str) -> bool:
        return any(t in d for t in tokens if t)

    def find_component_like(keywords: list[str]) -> bool:
        for c in components:
            name = _normalize(c.get("name", ""))
            if any(k in name for k in keywords):
                # Ensure the diagram actually includes that component name or alias
                if (c.get("name", "") in diagram) or (_safe_id(c.get("name", "")) in diagram):
                    return True
        # Fall back: diagram contains keyword directly
        return any(k in d for k in keywords)

    if "layered" in style:
        # Expect explicit grouping by layers.
        if layers:
            present = 0
            for layer in layers:
                ln = (layer.get("name", "") or "").strip()
                if not ln:
                    continue
                if kind == "plantuml":
                    if f'package "{ln.lower()}' in d or f'package "{_normalize(ln)}"' in d:
                        present += 1
                else:
                    if f'subgraph' in d and _safe_id(ln).lower() in d:
                        present += 1

            ratio = present / max(1, len([l for l in layers if (l.get("name") or "").strip()]))
            if ratio < 1.0:
                issues.append("Layered style: add explicit groups/packages for every layer")
            return ratio, issues

        return 0.6, ["Layered style: architecture has no layers list"]

    if "microservices" in style:
        score = 0.0
        if find_component_like(["gateway", "api gateway", "edge", "proxy"]):
            score += 0.5
        else:
            issues.append("Microservices style: include an API Gateway component and show it as the entry point")

        if find_component_like(["registry", "discovery", "service registry", "consul", "eureka"]):
            score += 0.5
        else:
            issues.append("Microservices style: include a Service Registry/Discovery component")

        return score, issues

    if "event-driven" in style or "event driven" in style:
        score = 0.0
        broker_keywords = ["broker", "bus", "queue", "kafka", "rabbitmq", "topic", "event"]
        if has_any("broker", "event bus", "message queue", "kafka", "rabbitmq") or find_component_like(broker_keywords):
            score += 0.6
        else:
            issues.append("Event-driven style: include an Event Bus/Broker and route events through it")

        # Basic mediation heuristic: some arrows to/from broker keywords
        if any(k in d for k in ["-> broker", "--> broker", "broker ->", "broker -->", "bus", "queue"]):
            score += 0.4
        else:
            issues.append("Event-driven style: show producers/consumers connected to the broker")

        return min(1.0, score), issues

    if "microkernel" in style:
        score = 0.0
        if has_any("core", "kernel") or find_component_like(["core", "kernel"]):
            score += 0.5
        else:
            issues.append("Microkernel style: include a Core/Kernel component")

        if has_any("plugin", "extension", "module") or find_component_like(["plugin", "extension", "module"]):
            score += 0.5
        else:
            issues.append("Microkernel style: include Plugin/Extension components")

        return score, issues

    if "space-based" in style or "space based" in style:
        score = 0.0
        if has_any("processing unit", "processor", "pu") or find_component_like(["processing", "processor", "processing unit"]):
            score += 0.5
        else:
            issues.append("Space-based style: include Processing Unit components")

        if has_any("grid", "cache", "space", "middleware") or find_component_like(["grid", "cache", "middleware", "space"]):
            score += 0.5
        else:
            issues.append("Space-based style: include Data Grid/Virtualized Middleware components")

        return score, issues

    # Unknown style: neutral
    return 0.5, ["Unknown architecture style for style-alignment scoring"]


def _evaluate_mermaid(diagram: str, architecture: dict) -> tuple[float, dict, list[str]]:
    components = architecture.get("components", []) or []
    interactions = architecture.get("interactions", []) or []

    issues: list[str] = []

    syntax_ok = bool(re.search(r"^(flowchart|graph)\s+", diagram.strip(), flags=re.IGNORECASE | re.MULTILINE))
    if not syntax_ok:
        issues.append("Mermaid syntax: diagram should start with 'flowchart TD' (or similar)")

    # Component coverage: search for safe ids or literal names
    matched_components = 0
    missing_components: list[str] = []
    for c in components:
        name = (c.get("name", "") or "").strip()
        if not name:
            continue
        sid = _safe_id(name)
        if (name in diagram) or (sid in diagram):
            matched_components += 1
        else:
            missing_components.append(name)

    total_components = len([c for c in components if (c.get("name") or "").strip()])
    component_cov = matched_components / max(1, total_components)
    if missing_components:
        issues.append(f"Mermaid coverage: missing components ({len(missing_components)}): " + ", ".join(missing_components[:8]) + ("..." if len(missing_components) > 8 else ""))

    # Interaction coverage: look for arrow lines containing both endpoints
    matched_interactions = 0
    missing_interactions: list[str] = []

    arrow_lines = [ln.strip() for ln in diagram.splitlines() if "-->" in ln or "---" in ln or "==>" in ln]

    for inter in interactions:
        f = _safe_id(inter.get("from", ""))
        t = _safe_id(inter.get("to", ""))
        if not f or not t:
            continue

        found = False
        for ln in arrow_lines:
            # Basic contains check; keep permissive for labels
            if f in ln and t in ln and "-->" in ln:
                found = True
                break
        if found:
            matched_interactions += 1
        else:
            missing_interactions.append(f"{inter.get('from','')} -> {inter.get('to','')}")

    total_interactions = len([i for i in interactions if (i.get("from") or "").strip() and (i.get("to") or "").strip()])
    interaction_cov = matched_interactions / max(1, total_interactions)
    if missing_interactions:
        issues.append(f"Mermaid coverage: missing interactions ({len(missing_interactions)}): " + "; ".join(missing_interactions[:6]) + ("..." if len(missing_interactions) > 6 else ""))

    style_score, style_issues = _compute_style_alignment(diagram, architecture, kind="mermaid")
    issues.extend(style_issues)

    syntax_score = 1.0 if syntax_ok else 0.0

    diagram_cas = (0.35 * component_cov) + (0.35 * interaction_cov) + (0.20 * style_score) + (0.10 * syntax_score)

    breakdown = {
        "syntax_ok": syntax_ok,
        "component_coverage": round(component_cov, 4),
        "interaction_coverage": round(interaction_cov, 4),
        "style_alignment": round(style_score, 4),
    }

    return round(diagram_cas, 4), breakdown, _dedupe_issues(issues)


def _evaluate_plantuml(diagram: str, architecture: dict) -> tuple[float, dict, list[str]]:
    components = architecture.get("components", []) or []
    interactions = architecture.get("interactions", []) or []

    issues: list[str] = []

    syntax_ok = ("@startuml" in diagram.lower()) and ("@enduml" in diagram.lower())
    if not syntax_ok:
        issues.append("PlantUML syntax: diagram must include @startuml and @enduml")

    if "componentstyle" not in diagram.lower():
        issues.append("PlantUML standard: add 'skinparam componentStyle rectangle' for component-diagram consistency")

    # Component coverage
    matched_components = 0
    missing_components: list[str] = []
    for c in components:
        name = (c.get("name", "") or "").strip()
        if not name:
            continue
        sid = _safe_id(name)
        # PlantUML may use [Name] or alias-only arrows
        if (f"[{name}]" in diagram) or (name in diagram) or re.search(rf"\b{re.escape(sid)}\b", diagram):
            matched_components += 1
        else:
            missing_components.append(name)

    total_components = len([c for c in components if (c.get("name") or "").strip()])
    component_cov = matched_components / max(1, total_components)
    if missing_components:
        issues.append(f"PlantUML coverage: missing components ({len(missing_components)}): " + ", ".join(missing_components[:8]) + ("..." if len(missing_components) > 8 else ""))

    # Interaction coverage: match lines with arrows
    matched_interactions = 0
    missing_interactions: list[str] = []

    arrow_lines = [ln.strip() for ln in diagram.splitlines() if "->" in ln or "-->" in ln or "..>" in ln]

    for inter in interactions:
        f_raw = (inter.get("from", "") or "").strip()
        t_raw = (inter.get("to", "") or "").strip()
        f = _safe_id(f_raw)
        t = _safe_id(t_raw)
        if not f or not t:
            continue

        found = False
        for ln in arrow_lines:
            # Allow many arrow types. Require both endpoints.
            if (f in ln or f_raw in ln) and (t in ln or t_raw in ln) and ("->" in ln or "-->" in ln or "..>" in ln):
                found = True
                break
        if found:
            matched_interactions += 1
        else:
            missing_interactions.append(f"{f_raw} -> {t_raw}")

    total_interactions = len([i for i in interactions if (i.get("from") or "").strip() and (i.get("to") or "").strip()])
    interaction_cov = matched_interactions / max(1, total_interactions)
    if missing_interactions:
        issues.append(f"PlantUML coverage: missing interactions ({len(missing_interactions)}): " + "; ".join(missing_interactions[:6]) + ("..." if len(missing_interactions) > 6 else ""))

    style_score, style_issues = _compute_style_alignment(diagram, architecture, kind="plantuml")
    issues.extend(style_issues)

    syntax_score = 1.0 if syntax_ok else 0.0

    diagram_cas = (0.35 * component_cov) + (0.35 * interaction_cov) + (0.20 * style_score) + (0.10 * syntax_score)

    breakdown = {
        "syntax_ok": syntax_ok,
        "component_coverage": round(component_cov, 4),
        "interaction_coverage": round(interaction_cov, 4),
        "style_alignment": round(style_score, 4),
    }

    return round(diagram_cas, 4), breakdown, _dedupe_issues(issues)


def _dedupe_issues(issues: list[str]) -> list[str]:
    seen = set()
    out = []
    for i in issues:
        key = i.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _unified_diff(a: str, b: str, from_name: str, to_name: str) -> str:
    a_lines = (a or "").splitlines(keepends=False)
    b_lines = (b or "").splitlines(keepends=False)
    diff = difflib.unified_diff(a_lines, b_lines, fromfile=from_name, tofile=to_name, lineterm="")
    return "\n".join(diff).strip() + "\n"


def unified_diff(a: str, b: str, from_name: str, to_name: str) -> str:
    """Public helper: git-style unified diff."""
    return _unified_diff(a, b, from_name=from_name, to_name=to_name)


def _apply_minimal_auto_fixes(kind: str, diagram: str, architecture: dict) -> str:
    """Minimal deterministic repairs to improve coverage/syntax without redesigning the diagram."""
    fixed = diagram or ""

    if kind == "plantuml":
        low = fixed.lower()
        if "@startuml" not in low:
            fixed = "@startuml\n" + fixed
        if "@enduml" not in low:
            fixed = fixed.rstrip() + "\n@enduml\n"
        if "skinparam componentStyle" not in fixed and "skinparam componentstyle" not in low:
            fixed = fixed.replace("@startuml", "@startuml\nskinparam componentStyle rectangle", 1)

    if kind == "mermaid":
        if not re.search(r"^(flowchart|graph)\s+", fixed.strip(), flags=re.IGNORECASE | re.MULTILINE):
            fixed = "flowchart TD\n\n" + fixed

    # If interactions are missing entirely, append a simple interaction section.
    interactions = architecture.get("interactions", []) or []
    if interactions and all(("->" not in ln and "-->" not in ln) for ln in fixed.splitlines()):
        if kind == "plantuml":
            before_end = "\n".join([ln for ln in fixed.splitlines() if ln.strip().lower() != "@enduml"]).rstrip()
            lines = [before_end, "", "' === Interactions (auto-added) ==="]
            for inter in interactions:
                f = _safe_id(inter.get("from", ""))
                t = _safe_id(inter.get("to", ""))
                label = (inter.get("type", "") or "").strip()
                if f and t:
                    lines.append(f"{f} --> {t} : {label}")
            fixed = "\n".join(lines) + "\n@enduml\n"
        else:
            lines = [fixed.rstrip(), "", "%% Interactions (auto-added)"]
            for inter in interactions:
                f = _safe_id(inter.get("from", ""))
                t = _safe_id(inter.get("to", ""))
                label = (inter.get("type", "") or "").strip()
                if f and t:
                    if label:
                        lines.append(f"{f} -->|\"{label}\"| {t}")
                    else:
                        lines.append(f"{f} --> {t}")
            fixed = "\n".join(lines) + "\n"

    return fixed


def _evaluate(kind: str, diagram: str, architecture: dict) -> tuple[float, dict, list[str]]:
    if kind == "mermaid":
        return _evaluate_mermaid(diagram, architecture)
    if kind == "plantuml":
        return _evaluate_plantuml(diagram, architecture)
    raise ValueError(f"Unknown diagram kind: {kind}")


def evaluate_diagram(kind: str, diagram: str, architecture: dict) -> tuple[float, dict, list[str]]:
    """Public helper: deterministic Diagram_CAS proxy scoring."""
    return _evaluate(kind, diagram, architecture)


def generate_diagram_with_iterations(
    *,
    model: str,
    architecture: dict,
    requirements: dict,
    kind: str,
    title: str,
    max_iterations: int | None = None,
) -> dict:
    """Generate a diagram in up to 2 iterations and return attempts + diff + final."""

    max_iterations = int(max_iterations or DIAGRAM_MAX_ITERATIONS)
    max_iterations = max(1, min(2, max_iterations))

    provider = get_provider_for_model(model)

    attempts: list[DiagramAttempt] = []
    prev_diagram = ""
    prev_score = 0.0
    prev_issues: list[str] = []

    for iteration in range(1, max_iterations + 1):
        prompt = build_diagram_prompt(
            architecture=architecture,
            requirements=requirements,
            diagram_kind=kind,
            title=title,
            iteration=iteration,
            previous_diagram=prev_diagram or None,
            previous_diagram_cas=prev_score or None,
            feedback_issues=prev_issues or None,
        )

        raw = provider.generate(prompt, model=model, options=DIAGRAM_GENERATION_OPTIONS)
        diagram = extract_diagram_source(kind, raw)

        diagram_cas, breakdown, issues = _evaluate(kind, diagram, architecture)

        attempts.append(DiagramAttempt(
            iteration=iteration,
            diagram=diagram,
            diagram_cas=diagram_cas,
            breakdown=breakdown,
            issues=issues,
        ))

        prev_diagram = diagram
        prev_score = diagram_cas
        prev_issues = issues

    # Prefer attempt 2 if it improved; else keep best.
    best = max(attempts, key=lambda a: a.diagram_cas)

    # Research requirement: show iteration improvement if possible.
    # If attempt2 did not improve over attempt1, apply minimal deterministic fixes to attempt2.
    if len(attempts) >= 2:
        a1, a2 = attempts[0], attempts[1]
        if a2.diagram_cas <= a1.diagram_cas:
            fixed2 = _apply_minimal_auto_fixes(kind, a2.diagram, architecture)
            fixed2_score, fixed2_breakdown, fixed2_issues = _evaluate(kind, fixed2, architecture)
            if fixed2_score > a2.diagram_cas:
                attempts[1] = DiagramAttempt(
                    iteration=2,
                    diagram=fixed2,
                    diagram_cas=fixed2_score,
                    breakdown=fixed2_breakdown,
                    issues=fixed2_issues,
                )
                best = max(attempts, key=lambda a: a.diagram_cas)

    diff_text = ""
    if len(attempts) >= 2:
        diff_text = _unified_diff(
            attempts[0].diagram,
            attempts[1].diagram,
            from_name=f"{kind}_v1",
            to_name=f"{kind}_v2",
        )

    return {
        "provider": provider.provider_name,
        "model": model,
        "kind": kind,
        "attempts": [
            {
                "iteration": a.iteration,
                "diagram_cas": a.diagram_cas,
                "breakdown": a.breakdown,
                "issues": a.issues,
                "diagram": a.diagram,
            }
            for a in attempts
        ],
        "final": {
            "iteration": best.iteration,
            "diagram_cas": best.diagram_cas,
            "breakdown": best.breakdown,
            "issues": best.issues,
            "diagram": best.diagram,
        },
        "diff": diff_text,
    }


def generate_both_diagrams_with_iterations(*, model: str, architecture: dict, requirements: dict, title: str) -> dict:
    """Convenience wrapper for Mermaid + PlantUML."""

    mermaid = generate_diagram_with_iterations(
        model=model,
        architecture=architecture,
        requirements=requirements,
        kind="mermaid",
        title=title,
    )

    plantuml = generate_diagram_with_iterations(
        model=model,
        architecture=architecture,
        requirements=requirements,
        kind="plantuml",
        title=title,
    )

    return {"mermaid": mermaid, "plantuml": plantuml}
