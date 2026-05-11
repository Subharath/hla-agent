"""
HLA Agent — Evaluation Report Generator
Produces a professional Markdown report with ranked tables,
winner analysis, and per-metric explanations.
"""

from datetime import datetime


def generate_report(ranked_candidates: list, requirements: dict,
                    run_id: str = "", diagram_meta: dict | None = None) -> str:
    """
    Generate a full Markdown evaluation report.

    Args:
        ranked_candidates: Sorted list from rank_candidates()
        requirements: Original requirements dict
        run_id: Optional run identifier

    Returns:
        Complete Markdown report string
    """
    project = requirements.get("project", "Unknown Project")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = []
    lines.append(f"# HLA Agent — Architecture Evaluation Report")
    lines.append(f"")
    lines.append(f"**Project:** {project}  ")
    lines.append(f"**Generated:** {timestamp}  ")
    if run_id:
        lines.append(f"**Run ID:** {run_id}  ")
    lines.append(f"**Candidates Evaluated:** {len(ranked_candidates)}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # === Ranking Table ===
    lines.append("## 📊 Candidate Rankings")
    lines.append("")
    lines.append("| Rank | Model | Style | RCR | NAS | SMI | LSCS | SCI | **CAS** | Verdict |")
    lines.append("|------|-------|-------|-----|-----|-----|------|-----|---------|---------|")

    for c in ranked_candidates:
        s = c.get("scores", {})
        verdict_icon = {"Accepted": "✅", "Marginal": "⚠️", "Poor": "❌"}.get(
            s.get("verdict", ""), "❓"
        )
        lines.append(
            f"| {c['rank']} | {c['model']} | {c.get('architecture', {}).get('architecture_style', 'N/A')} "
            f"| {s.get('RCR', 0):.2f} | {s.get('NAS', 0):.2f} | {s.get('SMI', 0):.2f} "
            f"| {s.get('LSCS', 0):.2f} | {s.get('SCI', 0):.2f} "
            f"| **{s.get('CAS', 0):.4f}** | {verdict_icon} {s.get('verdict', '')} |"
        )

    lines.append("")
    lines.append("---")
    lines.append("")

    # === Winner Analysis ===
    if ranked_candidates:
        winner = ranked_candidates[0]
        ws = winner.get("scores", {})
        wa = winner.get("architecture", {})

        lines.append("## 🏆 Winner Analysis")
        lines.append("")
        lines.append(f"- **Model:** {winner['model']}")
        lines.append(f"- **Architecture Style:** {wa.get('architecture_style', 'N/A')}")
        lines.append(f"- **CAS Score:** {ws.get('CAS', 0):.4f}")
        lines.append(f"- **Verdict:** {ws.get('verdict', 'N/A')}")
        lines.append(f"- **Components:** {len(wa.get('components', []))}")
        lines.append(f"- **Interactions:** {len(wa.get('interactions', []))}")
        lines.append(f"- **Layers:** {len(wa.get('layers', []))}")
        lines.append("")

        # Component list
        lines.append("### Components")
        lines.append("")
        lines.append("| Component | Layer | Responsibility |")
        lines.append("|-----------|-------|----------------|")
        for comp in wa.get("components", []):
            lines.append(
                f"| {comp.get('name', '')} | {comp.get('layer', '')} "
                f"| {comp.get('responsibility', '')} |"
            )
        lines.append("")

    # === Diagram Evidence (optional) ===
    if diagram_meta and diagram_meta.get("diagram_workflow"):
        wf = diagram_meta.get("diagram_workflow") or {}
        pu = (wf.get("plantuml") or {})
        mm = (wf.get("mermaid") or {})
        cur = (pu.get("current") or {})

        lines.append("---")
        lines.append("")
        lines.append("## 🧩 Diagram Workflow (Manual PlantUML → Approve → Mermaid)")
        lines.append("")
        lines.append(f"- **PlantUML Approved:** {str(bool(pu.get('approved')))}")
        lines.append(f"- **LLM Iterations Used:** {pu.get('llm_iterations_used', 'N/A')} / {pu.get('max_llm_iterations', 'N/A')}")
        if cur:
            lines.append(f"- **Current PlantUML Diagram_CAS:** {cur.get('diagram_cas', 0):.4f}")
            b = (cur.get("breakdown") or {})
            lines.append(
                f"- **PlantUML Breakdown:** syntax_ok={b.get('syntax_ok', False)} | "
                f"component_cov={b.get('component_coverage', 0):.4f} | "
                f"interaction_cov={b.get('interaction_coverage', 0):.4f} | "
                f"style_align={b.get('style_alignment', 0):.4f}"
            )
        lines.append("")

        if not bool(mm.get("generated")):
            lines.append("- **Mermaid:** Pending (generated only after PlantUML approval)")
        else:
            mcur = (mm.get("current") or {})
            lines.append(f"- **Mermaid Generated:** True (Diagram_CAS={mcur.get('diagram_cas', 0):.4f})")
        lines.append("")

    elif diagram_meta:
        lines.append("---")
        lines.append("")
        lines.append("## 🧩 Diagram Generation (LLM, max 2 iterations)")
        lines.append("")
        lines.append(
            "This section reports *diagram* iteration quality signals. "
            "`Diagram_CAS` is a deterministic proxy score (coverage + style-alignment + syntax), "
            "and is separate from the architecture CAS."
        )
        lines.append("")

        for kind in ["mermaid", "plantuml"]:
            if kind not in diagram_meta:
                continue

            info = diagram_meta.get(kind, {}) or {}
            final = info.get("final", {}) or {}
            attempts = info.get("attempts", []) or []

            lines.append(f"### {kind.title()}")
            lines.append("")
            lines.append(f"- **Model:** {info.get('model', 'N/A')}")
            lines.append(f"- **Provider:** {info.get('provider', 'N/A')}")
            lines.append(f"- **Final Diagram_CAS:** {final.get('diagram_cas', 0):.4f}")
            lines.append("")

            if attempts:
                lines.append("| Iteration | Diagram_CAS | Syntax OK | Component Cov | Interaction Cov | Style Align |")
                lines.append("|-----------|------------|-----------|---------------|----------------|-------------|")
                for a in attempts:
                    b = (a.get("breakdown", {}) or {})
                    lines.append(
                        f"| {a.get('iteration', '?')} | {a.get('diagram_cas', 0):.4f} "
                        f"| {str(b.get('syntax_ok', False))} "
                        f"| {b.get('component_coverage', 0):.4f} "
                        f"| {b.get('interaction_coverage', 0):.4f} "
                        f"| {b.get('style_alignment', 0):.4f} |"
                    )
                lines.append("")

            diff_text = (info.get("diff", "") or "").strip("\n")
            if diff_text:
                lines.append(f"#### {kind.title()} — Iteration Diff (v1 → v2)")
                lines.append("")
                lines.append("```diff")
                lines.append(diff_text)
                lines.append("```")
                lines.append("")

    # === Metric Details ===
    lines.append("---")
    lines.append("")
    lines.append("## 📈 Metric Definitions")
    lines.append("")
    lines.append("| Metric | Full Name | Weight | Threshold |")
    lines.append("|--------|-----------|--------|-----------|")
    lines.append("| RCR | Requirement Coverage Ratio | 25% | ≥ 0.80 |")
    lines.append("| NAS | NFR Alignment Score (Deterministic Rules Engine) | 25% | ≥ 0.75 |")
    lines.append("| SMI | Structural Modularity Index | 20% | ≥ 0.75 |")
    lines.append("| LSCS | Layer Separation Consistency Score | 15% | ≥ 0.90 |")
    lines.append("| SCI | Structural Clarity Index | 15% | ≥ 0.80 |")
    lines.append("")
    lines.append("**Phase 1 CAS** = 0.50×RCR + 0.50×NAS (tradeoff selection gate)")
    lines.append("")
    lines.append("**Phase 2 CAS** = 0.25×RCR + 0.25×NAS + 0.20×SMI + 0.15×LSCS + 0.15×SCI")
    lines.append("")
    lines.append("LSCS is style-aware for Layered, Event-Driven, Microkernel, Microservices, and Space-Based architectures.")
    lines.append("")
    lines.append("---")
    lines.append(f"*Report generated by HLA Agent v1.0*")

    return "\n".join(lines)
