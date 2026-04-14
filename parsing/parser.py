"""
HLA Agent — Architecture Output Parser
Extracts JSON from raw LLM text, validates structure,
normalizes fields for consistent downstream processing.
"""

import re
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ParseError(Exception):
    """Raised when LLM output cannot be parsed into valid architecture JSON."""
    pass


# Required top-level fields in architecture JSON
REQUIRED_FIELDS = ["architecture_style", "layers", "components", "interactions"]

# Required fields in each component
REQUIRED_COMPONENT_FIELDS = ["name", "layer", "responsibility"]

# Required fields in each interaction
REQUIRED_INTERACTION_FIELDS = ["from", "to", "type"]


def extract_json_from_text(raw_text: str) -> str:
    """
    Extract JSON from raw LLM text that may contain markdown fences,
    preamble text, or trailing explanations.

    Strategy (in order):
      1. Look for ```json ... ``` code fence
      2. Look for ``` ... ``` generic code fence
      3. Look for first { ... last } (greedy brace matching)
      4. Try the raw text as-is
    """
    if not raw_text or not raw_text.strip():
        raise ParseError("Empty response from LLM")

    text = raw_text.strip()

    # Strategy 1: ```json ... ``` fence
    json_fence = re.search(r'```json\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
    if json_fence:
        return json_fence.group(1).strip()

    # Strategy 2: ``` ... ``` generic fence
    generic_fence = re.search(r'```\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
    if generic_fence:
        candidate = generic_fence.group(1).strip()
        if candidate.startswith("{"):
            return candidate

    # Strategy 3: First { to last } (greedy brace matching)
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return text[first_brace:last_brace + 1]

    # Strategy 4: Try raw text as-is
    return text


def validate_architecture(data: dict) -> list[str]:
    """
    Validate that the parsed architecture has all required fields and structure.

    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []

    # Check required top-level fields
    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"Missing required field: '{field}'")

    if errors:
        return errors  # Can't validate further without top-level fields

    # Validate architecture_style
    style = data.get("architecture_style", "")
    if not isinstance(style, str) or not style.strip():
        errors.append("'architecture_style' must be a non-empty string")

    # Validate layers
    layers = data.get("layers", [])
    if not isinstance(layers, list) or len(layers) < 2:
        errors.append("'layers' must be a list with at least 2 layers")
    else:
        layer_names = set()
        for i, layer in enumerate(layers):
            if not isinstance(layer, dict):
                errors.append(f"Layer {i} must be a dictionary")
                continue
            name = layer.get("name", "")
            if not name:
                errors.append(f"Layer {i} missing 'name'")
            else:
                layer_names.add(name.lower().strip())

    # Validate components
    components = data.get("components", [])
    if not isinstance(components, list) or len(components) < 3:
        errors.append("'components' must be a list with at least 3 components")
    else:
        component_names = set()
        for i, comp in enumerate(components):
            if not isinstance(comp, dict):
                errors.append(f"Component {i} must be a dictionary")
                continue
            for field in REQUIRED_COMPONENT_FIELDS:
                if field not in comp or not comp[field]:
                    errors.append(f"Component {i} missing '{field}'")
            if "name" in comp:
                component_names.add(comp["name"])

    # Validate interactions
    interactions = data.get("interactions", [])
    if not isinstance(interactions, list):
        errors.append("'interactions' must be a list")
    elif len(interactions) < 2:
        errors.append("'interactions' should have at least 2 interactions")
    else:
        for i, inter in enumerate(interactions):
            if not isinstance(inter, dict):
                errors.append(f"Interaction {i} must be a dictionary")
                continue
            for field in REQUIRED_INTERACTION_FIELDS:
                if field not in inter or not inter[field]:
                    errors.append(f"Interaction {i} missing '{field}'")

    return errors


def normalize_architecture(data: dict) -> dict:
    """
    Normalize all field values for consistent downstream processing.
    - Strips whitespace
    - Ensures all layers have 'order' field
    - Ensures all interactions have 'direction' field
    - Builds lookup indices
    """
    # Normalize architecture style
    data["architecture_style"] = data.get("architecture_style", "").strip()

    # Normalize layers — ensure order exists
    layers = data.get("layers", [])
    for i, layer in enumerate(layers):
        layer["name"] = layer.get("name", "").strip()
        if "order" not in layer:
            layer["order"] = i + 1

    # Sort layers by order
    data["layers"] = sorted(layers, key=lambda l: l.get("order", 0))

    # Build layer name set for reference
    layer_names = {l["name"].lower() for l in data["layers"]}

    # Normalize components
    components = data.get("components", [])
    for comp in components:
        comp["name"] = comp.get("name", "").strip()
        comp["layer"] = comp.get("layer", "").strip()
        comp["responsibility"] = comp.get("responsibility", "").strip()

        # Try to fix layer assignment if it doesn't match any layer
        if comp["layer"].lower() not in layer_names:
            # Fuzzy match: find closest layer name
            comp_layer_lower = comp["layer"].lower()
            for ln in layer_names:
                if comp_layer_lower in ln or ln in comp_layer_lower:
                    comp["layer"] = next(
                        l["name"] for l in data["layers"]
                        if l["name"].lower() == ln
                    )
                    break

    data["components"] = components

    # Normalize interactions
    interactions = data.get("interactions", [])
    component_names = {c["name"] for c in components}

    for inter in interactions:
        inter["from"] = inter.get("from", "").strip()
        inter["to"] = inter.get("to", "").strip()
        inter["type"] = inter.get("type", "REST").strip()
        if "direction" not in inter:
            inter["direction"] = "down"  # Default assumption

    data["interactions"] = interactions

    return data


def parse_architecture(raw_text: str) -> dict:
    """
    Main entry point: extract, parse, validate, and normalize architecture JSON.

    Args:
        raw_text: Raw LLM output text

    Returns:
        Validated and normalized architecture dictionary

    Raises:
        ParseError: If parsing or validation fails
    """
    # Step 1: Extract JSON string
    json_str = extract_json_from_text(raw_text)

    # Step 2: Parse JSON
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        # Try to fix common JSON issues
        json_str_fixed = _attempt_json_fix(json_str)
        try:
            data = json.loads(json_str_fixed)
        except json.JSONDecodeError:
            raise ParseError(f"Invalid JSON: {e}\nExtracted text:\n{json_str[:500]}")

    if not isinstance(data, dict):
        raise ParseError(f"Expected JSON object, got {type(data).__name__}")

    # Step 3: Validate
    errors = validate_architecture(data)
    if errors:
        raise ParseError(
            f"Architecture validation failed with {len(errors)} errors:\n"
            + "\n".join(f"  • {e}" for e in errors)
        )

    # Step 4: Normalize
    data = normalize_architecture(data)

    logger.info(
        f"Parsed architecture: style={data['architecture_style']}, "
        f"{len(data['components'])} components, "
        f"{len(data['interactions'])} interactions"
    )

    return data


def _attempt_json_fix(json_str: str) -> str:
    """
    Attempt to fix common JSON formatting issues from LLM output.
    """
    fixed = json_str

    # Remove trailing commas before } or ]
    fixed = re.sub(r',\s*([}\]])', r'\1', fixed)

    # Fix single quotes → double quotes
    # (Only do this if there are no double quotes, to avoid breaking valid JSON)
    if '"' not in fixed and "'" in fixed:
        fixed = fixed.replace("'", '"')

    # Remove comments (// style)
    fixed = re.sub(r'//.*?$', '', fixed, flags=re.MULTILINE)

    # Remove BOM and other invisible characters
    fixed = fixed.encode('utf-8', errors='ignore').decode('utf-8')

    return fixed
