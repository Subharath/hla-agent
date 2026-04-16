"""
HLA Agent — SMI: Structural Modularity Index

Formula: SMI = 1 - (inter_module_edges / total_edges)

Groups components by layer. For each interaction, checks if 'from'
and 'to' components are in different layers (inter-module) or the
same layer (intra-module). High inter-module ratio = low modularity.
"""

import logging

logger = logging.getLogger(__name__)


def _build_component_layer_map(architecture: dict) -> dict[str, str]:
    """
    Build a mapping: component_name → layer_name (lowercase).
    """
    comp_to_layer = {}
    for comp in architecture.get("components", []):
        name = comp.get("name", "").strip()
        layer = comp.get("layer", "").strip().lower()
        if name:
            comp_to_layer[name] = layer
            # Also store lowercase version for fuzzy matching
            comp_to_layer[name.lower()] = layer
    return comp_to_layer


def compute_smi(architecture: dict) -> dict:
    """
    Compute Structural Modularity Index.

    Args:
        architecture: Parsed architecture dict with 'components' and 'interactions'

    Returns:
        {
            "score": float (0.0 - 1.0),
            "intra_module_edges": int,
            "inter_module_edges": int,
            "total_edges": int,
            "edge_details": [{ from, to, from_layer, to_layer, type }]
        }
    """
    interactions = architecture.get("interactions", [])
    comp_to_layer = _build_component_layer_map(architecture)

    if not interactions:
        # No interactions = perfectly modular (trivially)
        return {
            "score": 1.0,
            "intra_module_edges": 0,
            "inter_module_edges": 0,
            "total_edges": 0,
            "edge_details": [],
        }

    intra = 0
    inter = 0
    edge_details = []

    for interaction in interactions:
        from_comp = interaction.get("from", "").strip()
        to_comp = interaction.get("to", "").strip()

        # Resolve layers
        from_layer = comp_to_layer.get(from_comp, comp_to_layer.get(from_comp.lower(), "unknown"))
        to_layer = comp_to_layer.get(to_comp, comp_to_layer.get(to_comp.lower(), "unknown"))

        is_cross_layer = from_layer != to_layer

        if is_cross_layer:
            inter += 1
        else:
            intra += 1

        edge_details.append({
            "from": from_comp,
            "to": to_comp,
            "from_layer": from_layer,
            "to_layer": to_layer,
            "cross_layer": is_cross_layer,
        })

    total = intra + inter
    score = 1.0 - (inter / total) if total > 0 else 1.0

    # Clamp score to [0.0, 1.0]
    score = max(0.0, min(1.0, score))

    logger.info(
        f"SMI: {score:.3f} | Intra: {intra}, Inter: {inter}, Total: {total}"
    )

    return {
        "score": round(score, 4),
        "intra_module_edges": intra,
        "inter_module_edges": inter,
        "total_edges": total,
        "edge_details": edge_details,
    }
