"""Diagram Evaluator — Research-Grade Validation

Applies the same rigorous evaluation metrics (RCR, NAS, SMI, LSCS, SCI) 
used for architecture validation to diagram artifacts.

This ensures diagrams are not just syntactically correct but also:
- Architecturally complete (RCR)
- Quality-attribute aligned (NAS)
- Structurally modular (SMI)
- Topologically consistent (LSCS)
- Clearly documented (SCI)

Academic Positioning:
- Extends architecture evaluation to visual artifacts
- Provides auditable, deterministic scoring
- Supports research reproducibility
"""

from __future__ import annotations

import logging
from typing import Optional

from evaluation.rcr import compute_rcr
from evaluation.nas import compute_nas
from evaluation.smi import compute_smi
from evaluation.lscs import compute_lscs
from evaluation.sci import compute_sci
from evaluation.cas import compute_final_cas

logger = logging.getLogger(__name__)


def _extract_architecture_from_diagram(diagram: str, kind: str, original_architecture: dict) -> dict:
    """Reverse-engineer architecture structure from diagram source.
    
    This allows us to validate if the diagram faithfully represents the architecture.
    """
    import re
    
    # Start with original architecture as baseline
    extracted = {
        "architecture_style": original_architecture.get("architecture_style", ""),
        "layers": original_architecture.get("layers", []),
        "components": [],
        "interactions": [],
    }
    
    # Extract components from diagram
    if kind == "plantuml":
        # Match: [ComponentName] as alias
        comp_pattern = r'\[([^\]]+)\](?:\s+as\s+(\w+))?'
        for match in re.finditer(comp_pattern, diagram):
            comp_name = match.group(1).strip()
            # Find original component for responsibility
            orig_comp = next((c for c in original_architecture.get("components", []) 
                            if c.get("name", "") == comp_name), None)
            if orig_comp:
                extracted["components"].append(orig_comp)
        
        # Extract interactions: component1 --> component2 : label
        inter_pattern = r'(\w+)\s*(-+>|\.\.>)\s*(\w+)(?:\s*:\s*([^\n]+))?'
        for match in re.finditer(inter_pattern, diagram):
            from_comp = match.group(1).strip()
            to_comp = match.group(3).strip()
            label = (match.group(4) or "").strip()
            
            # Map aliases back to component names
            from_name = _resolve_component_name(from_comp, diagram, original_architecture)
            to_name = _resolve_component_name(to_comp, diagram, original_architecture)
            
            if from_name and to_name:
                extracted["interactions"].append({
                    "from": from_name,
                    "to": to_name,
                    "type": label or "Direct Call",
                    "direction": "down",  # Default assumption
                })
    
    elif kind == "mermaid":
        # Match: ComponentName["Label"] or ComponentName
        comp_pattern = r'(\w+)\[([^\]]+)\]'
        for match in re.finditer(comp_pattern, diagram):
            comp_id = match.group(1).strip()
            comp_label = match.group(2).strip().strip('"')
            
            orig_comp = next((c for c in original_architecture.get("components", []) 
                            if c.get("name", "") == comp_label or 
                            c.get("name", "").replace(" ", "_") == comp_id), None)
            if orig_comp:
                extracted["components"].append(orig_comp)
        
        # Extract interactions: A -->|label| B
        inter_pattern = r'(\w+)\s*--+>(?:\|"?([^"|]+)"?\|)?\s*(\w+)'
        for match in re.finditer(inter_pattern, diagram):
            from_id = match.group(1).strip()
            label = (match.group(2) or "").strip()
            to_id = match.group(3).strip()
            
            from_name = _resolve_component_name(from_id, diagram, original_architecture)
            to_name = _resolve_component_name(to_id, diagram, original_architecture)
            
            if from_name and to_name:
                extracted["interactions"].append({
                    "from": from_name,
                    "to": to_name,
                    "type": label or "Direct Call",
                    "direction": "down",
                })
    
    return extracted


def _resolve_component_name(identifier: str, diagram: str, architecture: dict) -> Optional[str]:
    """Resolve component identifier/alias to actual component name."""
    # Direct match
    for comp in architecture.get("components", []):
        name = comp.get("name", "")
        if name == identifier or name.replace(" ", "_") == identifier:
            return name
    
    # Fuzzy match on diagram declarations
    import re
    if "plantuml" in diagram.lower() or "@startuml" in diagram.lower():
        # Look for [Name] as identifier
        pattern = rf'\[([^\]]+)\]\s+as\s+{re.escape(identifier)}\b'
        match = re.search(pattern, diagram)
        if match:
            return match.group(1).strip()
    
    return identifier  # Fallback to identifier itself


def evaluate_diagram_with_metrics(
    *,
    diagram: str,
    kind: str,
    architecture: dict,
    requirements: dict,
) -> dict:
    """Evaluate diagram using full research-grade metrics.
    
    Args:
        diagram: Diagram source code (PlantUML or Mermaid)
        kind: "plantuml" or "mermaid"
        architecture: Original architecture JSON
        requirements: Requirements JSON with FRs and NFRs
    
    Returns:
        {
            "diagram_cas": float,
            "metrics": {
                "RCR": {...},
                "NAS": {...},
                "SMI": {...},
                "LSCS": {...},
                "SCI": {...}
            },
            "scores": {
                "RCR": float,
                "NAS": float,
                "SMI": float,
                "LSCS": float,
                "SCI": float,
                "CAS": float
            },
            "verdict": str,
            "issues": [str],
            "extracted_architecture": dict
        }
    """
    logger.info(f"Evaluating {kind} diagram with research-grade metrics")
    
    # Extract architecture from diagram
    extracted_arch = _extract_architecture_from_diagram(diagram, kind, architecture)
    
    # Apply all 5 metrics
    rcr_result = compute_rcr(extracted_arch, requirements)
    nas_result = compute_nas(extracted_arch, requirements)
    smi_result = compute_smi(extracted_arch)
    lscs_result = compute_lscs(extracted_arch)
    sci_result = compute_sci(extracted_arch)
    
    # Compute CAS
    scores = {
        "RCR": rcr_result["score"],
        "NAS": nas_result["score"],
        "SMI": smi_result["score"],
        "LSCS": lscs_result["score"],
        "SCI": sci_result["score"],
    }
    
    cas_result = compute_final_cas(scores)
    scores["CAS"] = cas_result["cas"]
    
    # Generate issues from metric results
    issues = []
    
    if rcr_result.get("uncovered"):
        issues.append(f"RCR: {len(rcr_result['uncovered'])} uncovered requirements: {', '.join(rcr_result['uncovered'][:5])}")
    
    if nas_result.get("unaligned"):
        issues.append(f"NAS: {len(nas_result['unaligned'])} unaligned NFRs: {', '.join(nas_result['unaligned'][:5])}")
    
    if smi_result.get("average_instability", 0) > 0.7:
        issues.append(f"SMI: High instability ({smi_result['average_instability']:.2f}) indicates tight coupling")
    
    if lscs_result.get("violations", 0) > 0:
        issues.append(f"LSCS: {lscs_result['violations']} structural violations detected")
        for v in lscs_result.get("violation_details", [])[:3]:
            issues.append(f"  - {v.get('reason', 'Unknown violation')}")
    
    if sci_result.get("valid", 0) < sci_result.get("total", 1):
        invalid_count = sci_result["total"] - sci_result["valid"]
        issues.append(f"SCI: {invalid_count} components lack proper naming/documentation")
    
    logger.info(f"Diagram CAS: {scores['CAS']:.4f} | Verdict: {cas_result['verdict']}")
    
    return {
        "diagram_cas": scores["CAS"],
        "metrics": {
            "RCR": rcr_result,
            "NAS": nas_result,
            "SMI": smi_result,
            "LSCS": lscs_result,
            "SCI": sci_result,
        },
        "scores": scores,
        "verdict": cas_result["verdict"],
        "issues": issues,
        "extracted_architecture": extracted_arch,
        "weighted_breakdown": cas_result["weighted_breakdown"],
        "below_threshold": cas_result["below_threshold"],
    }
