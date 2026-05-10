"""
HLA Agent — SMI: Structural Modularity Index

Overhauled to use Martin's Instability Metric.
Formula per component: I = Ce / (Ca + Ce)
Where:
- Ca (Afferent Coupling) = incoming edges (Fan-in)
- Ce (Efferent Coupling) = outgoing edges (Fan-out)

System SMI = 1 - Average(I)
High SMI means highly modular/stable architecture. Low SMI means highly coupled/unstable.
"""

import logging

logger = logging.getLogger(__name__)


def compute_smi(architecture: dict) -> dict:
    """
    Compute Structural Modularity Index using Martin's Instability.

    Args:
        architecture: Parsed architecture dict with 'components' and 'interactions'

    Returns:
        {
            "score": float (0.0 - 1.0),
            "average_instability": float,
            "total_components": int,
            "component_details": [{ name, Ca, Ce, instability }]
        }
    """
    components = architecture.get("components", [])
    interactions = architecture.get("interactions", [])

    if not components:
        return {
            "score": 1.0,
            "average_instability": 0.0,
            "total_components": 0,
            "component_details": [],
        }

    # Initialize coupling counts
    coupling = {comp.get("name", "").strip(): {"Ca": 0, "Ce": 0} for comp in components if comp.get("name")}

    # Calculate Fan-in (Ca) and Fan-out (Ce)
    for interaction in interactions:
        from_comp = interaction.get("from", "").strip()
        to_comp = interaction.get("to", "").strip()

        # Only count if the component is defined
        if from_comp in coupling:
            coupling[from_comp]["Ce"] += 1
        if to_comp in coupling:
            coupling[to_comp]["Ca"] += 1

    details = []
    total_instability = 0.0
    valid_comps = 0

    for name, counts in coupling.items():
        ca = counts["Ca"]
        ce = counts["Ce"]
        total_coupling = ca + ce

        # If a component is completely isolated, it is perfectly stable (I = 0)
        instability = (ce / total_coupling) if total_coupling > 0 else 0.0

        details.append({
            "name": name,
            "Ca": ca,
            "Ce": ce,
            "instability": round(instability, 4)
        })

        total_instability += instability
        valid_comps += 1

    avg_instability = (total_instability / valid_comps) if valid_comps > 0 else 0.0
    smi_score = 1.0 - avg_instability

    logger.info(
        f"SMI: {smi_score:.3f} | Avg Instability: {avg_instability:.3f} | Components: {valid_comps}"
    )

    return {
        "score": round(smi_score, 4),
        "average_instability": round(avg_instability, 4),
        "total_components": valid_comps,
        "component_details": details,
    }
