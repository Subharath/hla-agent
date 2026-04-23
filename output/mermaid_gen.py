"""
HLA Agent — Mermaid Diagram Generator
Generates .mmd diagrams from the winning architecture for GitHub/web embedding.
"""


def generate_mermaid(architecture: dict, title: str = "") -> str:
    """
    Generate Mermaid flowchart diagram from architecture JSON.

    Args:
        architecture: Parsed architecture dict (winner)
        title: Optional diagram title

    Returns:
        Mermaid source string (.mmd content)
    """
    style = architecture.get("architecture_style", "Architecture")
    layers = architecture.get("layers", [])
    components = architecture.get("components", [])
    interactions = architecture.get("interactions", [])

    lines = []
    lines.append("flowchart TD")
    lines.append("")

    # Group components by layer
    layer_components = {}
    for comp in components:
        layer = comp.get("layer", "Unknown")
        if layer not in layer_components:
            layer_components[layer] = []
        layer_components[layer].append(comp)

    # Create subgraphs for each layer
    for layer in layers:
        layer_name = layer.get("name", "Unknown")
        safe_name = layer_name.replace(" ", "_").replace("-", "_")
        comps = layer_components.get(layer_name, [])

        lines.append(f'    subgraph {safe_name}["{layer_name}"]')
        for comp in comps:
            comp_name = comp.get("name", "Unknown")
            comp_id = comp_name.replace(" ", "_").replace("-", "_")
            resp = comp.get("responsibility", "")
            short_resp = resp[:50] + "..." if len(resp) > 50 else resp
            lines.append(f'        {comp_id}["{comp_name}"]')
        lines.append("    end")
        lines.append("")

    # Add interactions
    lines.append("    %% Interactions")
    for inter in interactions:
        from_c = inter.get("from", "").replace(" ", "_").replace("-", "_")
        to_c = inter.get("to", "").replace(" ", "_").replace("-", "_")
        itype = inter.get("type", "")

        if itype:
            lines.append(f'    {from_c} -->|"{itype}"| {to_c}')
        else:
            lines.append(f'    {from_c} --> {to_c}')

    # Add styling
    lines.append("")
    lines.append("    %% Styling")

    colors = ["#1a5276", "#117a65", "#7d3c98", "#b9770e", "#922b21", "#1b4f72"]
    for i, layer in enumerate(layers):
        layer_name = layer.get("name", "Unknown")
        safe_name = layer_name.replace(" ", "_").replace("-", "_")
        color = colors[i % len(colors)]
        lines.append(f'    style {safe_name} fill:{color},color:#fff,stroke:#333')

    return "\n".join(lines)
