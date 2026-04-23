"""
HLA Agent — PlantUML Diagram Generator
Generates .puml component diagrams from the winning architecture.
"""


def generate_plantuml(architecture: dict, title: str = "") -> str:
    """
    Generate PlantUML component diagram from architecture JSON.

    Args:
        architecture: Parsed architecture dict (winner)
        title: Optional diagram title

    Returns:
        PlantUML source string (.puml content)
    """
    style = architecture.get("architecture_style", "Architecture")
    layers = architecture.get("layers", [])
    components = architecture.get("components", [])
    interactions = architecture.get("interactions", [])

    title = title or f"{style} Architecture"

    lines = []
    lines.append("@startuml")
    lines.append(f'title {title}')
    lines.append("")
    lines.append("skinparam componentStyle rectangle")
    lines.append("skinparam backgroundColor #FEFEFE")
    lines.append("skinparam package {")
    lines.append("  BackgroundColor #F0F4F8")
    lines.append("  BorderColor #2C3E50")
    lines.append("  FontColor #2C3E50")
    lines.append("  FontSize 14")
    lines.append("}")
    lines.append("skinparam component {")
    lines.append("  BackgroundColor #3498DB")
    lines.append("  FontColor #FFFFFF")
    lines.append("  BorderColor #2980B9")
    lines.append("}")
    lines.append("")

    # Group components by layer
    layer_components = {}
    for comp in components:
        layer = comp.get("layer", "Unknown")
        if layer not in layer_components:
            layer_components[layer] = []
        layer_components[layer].append(comp)

    # Create packages for each layer
    for layer in layers:
        layer_name = layer.get("name", "Unknown")
        alias = layer_name.replace(" ", "_").replace("-", "_")
        comps = layer_components.get(layer_name, [])

        lines.append(f'package "{layer_name}" as {alias} {{')
        for comp in comps:
            comp_name = comp.get("name", "Unknown")
            comp_alias = comp_name.replace(" ", "_").replace("-", "_")
            resp = comp.get("responsibility", "")
            lines.append(f'  [{comp_name}] as {comp_alias}')
            if resp:
                lines.append(f'  note right of {comp_alias} : {resp[:60]}')
        lines.append("}")
        lines.append("")

    # Add interactions
    lines.append("' === Interactions ===")
    for inter in interactions:
        from_c = inter.get("from", "").replace(" ", "_").replace("-", "_")
        to_c = inter.get("to", "").replace(" ", "_").replace("-", "_")
        itype = inter.get("type", "")
        lines.append(f'{from_c} --> {to_c} : {itype}')

    lines.append("")
    lines.append("@enduml")

    return "\n".join(lines)
