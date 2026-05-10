"""
HLA Agent — NAS: NFR Alignment Score

Overhauled to use Semantic LLM-as-a-Judge based on ATAM principles.
Instead of brittle keyword matching, we ask the LLM to evaluate the architecture's
ability to satisfy the specific NFRs based on architectural scenarios and mechanisms.
"""

import json
import logging
import traceback
from config import MODELS, GENERATION_OPTIONS
from providers import get_provider_for_model

logger = logging.getLogger(__name__)


def compute_nas(architecture: dict, requirements: dict, evaluator_model: str = None) -> dict:
    """
    Compute NFR Alignment Score using LLM-as-a-judge.

    Args:
        architecture: Parsed architecture dict
        requirements: Requirements dict with 'non_functional_requirements'
        evaluator_model: Model to use for evaluation (defaults to first available config model)

    Returns:
        {
            "score": float (0.0 - 1.0),
            "alignment_map": { nfr_id: { type, score, reasoning } },
            "unaligned": [nfr_ids]
        }
    """
    nfrs = requirements.get("non_functional_requirements", [])

    if not nfrs:
        return {"score": 1.0, "alignment_map": {}, "unaligned": []}

    evaluator_model = evaluator_model or MODELS[0]
    provider = get_provider_for_model(evaluator_model)

    # Build the prompt
    prompt = f"""
You are an expert Software Architect performing an Architecture Tradeoff Analysis Method (ATAM) evaluation.
Evaluate how well the provided Architecture Candidate satisfies the given Non-Functional Requirements (NFRs).

Architecture Candidate (JSON):
{json.dumps(architecture, indent=2)}

Non-Functional Requirements to Evaluate:
{json.dumps(nfrs, indent=2)}

For each NFR, analyze the architecture's components, layers, and interactions. Determine a score from 0.0 to 1.0:
- 1.0 = Excellent support (explicit mechanisms exist)
- 0.5 = Partial/Implicit support
- 0.0 = No support or architectural anti-pattern

RESPOND ONLY WITH VALID JSON in this exact format:
{{
  "NFR_ID_HERE": {{"score": 0.8, "reasoning": "Brief explanation of why..."}},
  "NFR_ID_HERE_2": {{"score": 0.0, "reasoning": "..."}}
}}
No markdown formatting, no backticks, just raw JSON.
"""

    alignment_map = {}
    unaligned = []
    total_score = 0.0

    try:
        logger.info(f"Evaluating NAS using LLM-as-a-judge ({evaluator_model})...")
        # Use low temperature for analytical evaluation
        eval_options = {**GENERATION_OPTIONS, "temperature": 0.1, "max_tokens": 1500}
        
        raw_response = provider.generate(prompt, evaluator_model, eval_options)
        
        # Clean markdown if present
        if raw_response.startswith("```json"):
            raw_response = raw_response[7:-3]
        elif raw_response.startswith("```"):
            raw_response = raw_response[3:-3]
            
        evaluation_result = json.loads(raw_response.strip())

        for nfr in nfrs:
            nfr_id = nfr.get("id")
            nfr_type = nfr.get("type", "")
            nfr_target = nfr.get("target", "")

            eval_data = evaluation_result.get(nfr_id, {})
            score = float(eval_data.get("score", 0.0))
            reasoning = eval_data.get("reasoning", "No evaluation provided by LLM.")

            total_score += score
            alignment_map[nfr_id] = {
                "type": nfr_type,
                "target": nfr_target,
                "score": score,
                "reasoning": reasoning,
            }

            if score < 0.5:
                unaligned.append(nfr_id)

    except Exception as e:
        logger.error(f"NAS LLM evaluation failed: {e}")
        logger.debug(traceback.format_exc())
        # Fallback to 0 if LLM fails
        for nfr in nfrs:
            nfr_id = nfr.get("id")
            alignment_map[nfr_id] = {
                "type": nfr.get("type", ""),
                "target": nfr.get("target", ""),
                "score": 0.0,
                "reasoning": "LLM evaluation failed.",
            }
            unaligned.append(nfr_id)

    final_score = total_score / len(nfrs) if nfrs else 0.0

    logger.info(
        f"NAS: {final_score:.3f} | "
        f"Aligned: {len(nfrs) - len(unaligned)}/{len(nfrs)} | "
        f"Unaligned: {unaligned}"
    )

    return {
        "score": round(final_score, 4),
        "alignment_map": alignment_map,
        "unaligned": unaligned,
    }
