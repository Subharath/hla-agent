"""Diagram workflow (manual PlantUML iteration → approve → Mermaid).

This module implements the user-driven UX:
- Generate an initial PlantUML diagram via LLM.
- Score it deterministically (Diagram_CAS proxy).
- Allow user manual edits (rescore) and optionally one LLM improvement pass (max 2 LLM iterations).
- Show unified diffs between revisions.
- Generate Mermaid only after PlantUML approval.

State is stored in results/diagram_workflow.json plus the current diagram files.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from config import RESULTS_DIR, DIAGRAM_GENERATION_OPTIONS, DIAGRAM_MAX_ITERATIONS
from providers import get_provider_for_model
from prompt.builder import build_diagram_prompt
from output.llm_diagram_gen import (
    extract_diagram_source,
    evaluate_diagram,
    unified_diff,
)
from output.mermaid_gen import generate_mermaid
from output.diagram_evaluator import evaluate_diagram_with_metrics
from output.side_by_side_diff import generate_side_by_side_diff

logger = logging.getLogger(__name__)

WORKFLOW_PATH = RESULTS_DIR / "diagram_workflow.json"
PLANTUML_PATH = RESULTS_DIR / "diagram.puml"  # current (draft or approved)
MERMAID_PATH = RESULTS_DIR / "diagram.mmd"    # only created after approval


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def load_workflow() -> Optional[dict]:
    if not WORKFLOW_PATH.exists():
        return None
    with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_workflow(state: dict) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    with open(WORKFLOW_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def _init_state(*, run_id: str, model: str, provider_name: str) -> dict:
    return {
        "run_id": run_id,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "model": model,
        "provider": provider_name,
        "plantuml": {
            "approved": False,
            "max_llm_iterations": max(1, min(2, int(DIAGRAM_MAX_ITERATIONS or 2))),
            "llm_iterations_used": 0,
            "current": None,
            "history": [],
            "last_diff": "",
        },
        "mermaid": {
            "generated": False,
            "current": None,
        },
    }


def _set_current(state: dict, *, kind: str, attempt: dict, diff_text: str) -> None:
    state["updated_at"] = _now_iso()
    state[kind]["current"] = attempt
    state[kind]["last_diff"] = diff_text or ""


def _append_history(state: dict, *, kind: str, attempt: dict) -> None:
    state[kind]["history"].append(attempt)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text or "")


def ensure_initial_plantuml(
    *,
    run_id: str,
    model: str,
    architecture: dict,
    requirements: dict,
    title: str,
    use_research_metrics: bool = True,
) -> dict:
    """Ensure a PlantUML v1 exists for this run (LLM-generated + scored).
    
    Args:
        use_research_metrics: If True, use full RCR/NAS/SMI/LSCS/SCI evaluation.
                             If False, use lightweight proxy scoring.
    """

    existing = load_workflow()
    if existing and existing.get("run_id") == run_id and existing.get("plantuml", {}).get("current"):
        return existing

    # If we already have a diagram.puml (e.g., fallback path), seed the workflow from it.
    if PLANTUML_PATH.exists():
        with open(PLANTUML_PATH, "r", encoding="utf-8") as f:
            seeded = f.read()
        seeded = extract_diagram_source("plantuml", seeded)
        
        # Use research-grade metrics for evaluation
        if use_research_metrics:
            eval_result = evaluate_diagram_with_metrics(
                diagram=seeded,
                kind="plantuml",
                architecture=architecture,
                requirements=requirements,
            )
            diagram_cas = eval_result["diagram_cas"]
            breakdown = eval_result["scores"]
            issues = eval_result["issues"]
            metrics_detail = eval_result["metrics"]
        else:
            diagram_cas, breakdown, issues = evaluate_diagram("plantuml", seeded, architecture)
            metrics_detail = None
        
        provider_name = get_provider_for_model(model).provider_name
        state = _init_state(run_id=run_id, model=model, provider_name=provider_name)
        attempt = {
            "timestamp": _now_iso(),
            "kind": "plantuml",
            "source": "seed",
            "llm_iteration": 0,
            "diagram": seeded,
            "diagram_cas": diagram_cas,
            "breakdown": breakdown,
            "issues": issues,
            "metrics_detail": metrics_detail,
        }
        _append_history(state, kind="plantuml", attempt=attempt)
        _set_current(state, kind="plantuml", attempt=attempt, diff_text="")
        save_workflow(state)
        return state

    provider = get_provider_for_model(model)
    state = _init_state(run_id=run_id, model=model, provider_name=provider.provider_name)

    prompt = build_diagram_prompt(
        architecture=architecture,
        requirements=requirements,
        diagram_kind="plantuml",
        title=title,
        iteration=1,
    )

    raw = provider.generate(prompt, model=model, options=DIAGRAM_GENERATION_OPTIONS)
    plantuml = extract_diagram_source("plantuml", raw)
    
    # Use research-grade metrics
    if use_research_metrics:
        eval_result = evaluate_diagram_with_metrics(
            diagram=plantuml,
            kind="plantuml",
            architecture=architecture,
            requirements=requirements,
        )
        diagram_cas = eval_result["diagram_cas"]
        breakdown = eval_result["scores"]
        issues = eval_result["issues"]
        metrics_detail = eval_result["metrics"]
    else:
        diagram_cas, breakdown, issues = evaluate_diagram("plantuml", plantuml, architecture)
        metrics_detail = None

    attempt = {
        "timestamp": _now_iso(),
        "kind": "plantuml",
        "source": "llm",
        "llm_iteration": 1,
        "diagram": plantuml,
        "diagram_cas": diagram_cas,
        "breakdown": breakdown,
        "issues": issues,
        "metrics_detail": metrics_detail,
    }

    state["plantuml"]["llm_iterations_used"] = 1
    _append_history(state, kind="plantuml", attempt=attempt)
    _set_current(state, kind="plantuml", attempt=attempt, diff_text="")

    _write_text(PLANTUML_PATH, plantuml)
    save_workflow(state)
    return state


def score_manual_plantuml_edit(*, run_id: str, plantuml: str, architecture: dict, requirements: dict) -> dict:
    state = load_workflow()
    if not state or state.get("run_id") != run_id:
        raise ValueError("Diagram workflow not initialized for this run")

    prev = (state.get("plantuml", {}).get("current") or {}).get("diagram") or ""
    cleaned = extract_diagram_source("plantuml", plantuml)
    
    # Use research-grade metrics
    eval_result = evaluate_diagram_with_metrics(
        diagram=cleaned,
        kind="plantuml",
        architecture=architecture,
        requirements=requirements,
    )
    diagram_cas = eval_result["diagram_cas"]
    breakdown = eval_result["scores"]
    issues = eval_result["issues"]
    metrics_detail = eval_result["metrics"]

    # Generate side-by-side diff
    if prev:
        diff_result = generate_side_by_side_diff(
            old_content=prev,
            new_content=cleaned,
            old_label="plantuml_prev",
            new_label="plantuml_edit",
        )
        diff_text = diff_result["unified"]
        diff_html = diff_result["html"]
        diff_stats = diff_result["statistics"]
    else:
        diff_text = ""
        diff_html = ""
        diff_stats = {}

    attempt = {
        "timestamp": _now_iso(),
        "kind": "plantuml",
        "source": "manual",
        "llm_iteration": state["plantuml"].get("llm_iterations_used", 0),
        "diagram": cleaned,
        "diagram_cas": diagram_cas,
        "breakdown": breakdown,
        "issues": issues,
        "metrics_detail": metrics_detail,
        "diff": diff_text,
        "diff_html": diff_html,
        "diff_stats": diff_stats,
    }

    _append_history(state, kind="plantuml", attempt=attempt)
    _set_current(state, kind="plantuml", attempt=attempt, diff_text=diff_text)
    _write_text(PLANTUML_PATH, cleaned)
    save_workflow(state)
    return state


def improve_plantuml_with_llm(
    *,
    run_id: str,
    model: str,
    architecture: dict,
    requirements: dict,
    title: str,
    user_notes: str | None = None,
) -> dict:
    """Ask the LLM for iteration 2 improvement (max 2 total LLM iterations)."""

    state = load_workflow()
    if not state or state.get("run_id") != run_id:
        raise ValueError("Diagram workflow not initialized for this run")

    if state.get("plantuml", {}).get("approved"):
        return state

    used = int(state["plantuml"].get("llm_iterations_used", 0))
    max_llm = int(state["plantuml"].get("max_llm_iterations", 2))
    if used >= max_llm:
        return state

    provider = get_provider_for_model(model)

    prev_attempt = state["plantuml"].get("current") or {}
    prev_diagram = prev_attempt.get("diagram") or ""
    prev_score = prev_attempt.get("diagram_cas")
    prev_issues = prev_attempt.get("issues") or []

    prompt = build_diagram_prompt(
        architecture=architecture,
        requirements=requirements,
        diagram_kind="plantuml",
        title=title,
        iteration=2,
        previous_diagram=prev_diagram,
        previous_diagram_cas=prev_score,
        feedback_issues=prev_issues,
        user_feedback=user_notes,
    )

    raw = provider.generate(prompt, model=model, options=DIAGRAM_GENERATION_OPTIONS)
    plantuml = extract_diagram_source("plantuml", raw)
    
    # Use research-grade metrics
    eval_result = evaluate_diagram_with_metrics(
        diagram=plantuml,
        kind="plantuml",
        architecture=architecture,
        requirements=requirements,
    )
    diagram_cas = eval_result["diagram_cas"]
    breakdown = eval_result["scores"]
    issues = eval_result["issues"]
    metrics_detail = eval_result["metrics"]

    # Generate side-by-side diff
    diff_result = generate_side_by_side_diff(
        old_content=prev_diagram,
        new_content=plantuml,
        old_label="plantuml_v1",
        new_label="plantuml_v2",
    )
    diff_text = diff_result["unified"]
    diff_html = diff_result["html"]
    diff_stats = diff_result["statistics"]

    attempt = {
        "timestamp": _now_iso(),
        "kind": "plantuml",
        "source": "llm",
        "llm_iteration": used + 1,
        "diagram": plantuml,
        "diagram_cas": diagram_cas,
        "breakdown": breakdown,
        "issues": issues,
        "metrics_detail": metrics_detail,
        "diff": diff_text,
        "diff_html": diff_html,
        "diff_stats": diff_stats,
        "user_notes": (user_notes or "").strip() or None,
    }

    state["provider"] = provider.provider_name
    state["model"] = model
    state["plantuml"]["llm_iterations_used"] = used + 1

    _append_history(state, kind="plantuml", attempt=attempt)
    _set_current(state, kind="plantuml", attempt=attempt, diff_text=diff_text)
    _write_text(PLANTUML_PATH, plantuml)
    save_workflow(state)
    return state


def approve_plantuml_and_generate_mermaid(
    *,
    run_id: str,
    model: str,
    architecture: dict,
    requirements: dict,
    title: str,
) -> dict:
    """Mark PlantUML approved, then generate Mermaid (simple + copyable)."""

    state = load_workflow()
    if not state or state.get("run_id") != run_id:
        raise ValueError("Diagram workflow not initialized for this run")

    state["plantuml"]["approved"] = True

    # Mermaid is intentionally deterministic to avoid Mermaid syntax drift.
    # It is derived from the winning architecture (and thus consistent with approved PlantUML).
    mermaid_src = generate_mermaid(architecture, title)
    diagram_cas, breakdown, issues = evaluate_diagram("mermaid", mermaid_src, architecture)
    attempt = {
        "timestamp": _now_iso(),
        "kind": "mermaid",
        "source": "deterministic",
        "diagram": mermaid_src,
        "diagram_cas": diagram_cas,
        "breakdown": breakdown,
        "issues": issues,
    }

    _write_text(MERMAID_PATH, mermaid_src)

    state["mermaid"]["generated"] = True
    state["mermaid"]["current"] = attempt

    save_workflow(state)
    return state


def public_workflow_view(state: dict) -> dict:
    """Return a UI-friendly view (no internal paths)."""

    if not state:
        return {}

    plantuml = state.get("plantuml", {}) or {}
    mermaid = state.get("mermaid", {}) or {}

    return {
        "run_id": state.get("run_id"),
        "model": state.get("model"),
        "provider": state.get("provider"),
        "updated_at": state.get("updated_at"),
        "plantuml": {
            "approved": bool(plantuml.get("approved")),
            "max_llm_iterations": int(plantuml.get("max_llm_iterations", 2)),
            "llm_iterations_used": int(plantuml.get("llm_iterations_used", 0)),
            "current": plantuml.get("current"),
            "last_diff": plantuml.get("last_diff", ""),
        },
        "mermaid": {
            "generated": bool(mermaid.get("generated")),
            "current": mermaid.get("current"),
        },
    }
