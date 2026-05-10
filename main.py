"""
HLA Agent — Main Pipeline Runner (CLI)
Orchestrates: load → prompt → generate → parse → evaluate → rank → output
"""

import sys
import json
import logging
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import (
    INPUT_DIR, RESULTS_DIR, MODELS, CANDIDATES_PER_MODEL,
    THRESHOLDS, MAX_REGENERATION_LOOPS, LLM_PROVIDER,
)
from prompt.builder import build_architecture_prompt, build_feedback_from_scores
from generation.generator import generate_all, regenerate_single, check_models_available
from parsing.parser import parse_architecture, ParseError
from evaluation import evaluate_architecture
from evaluation.cas import rank_candidates
from output.report import generate_report
from output.plantuml_gen import generate_plantuml
from output.mermaid_gen import generate_mermaid
from output.radar import generate_radar_chart
from storage.db import create_run, update_run, insert_candidate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("HLA-Agent")


def load_input(path: str) -> dict:
    """Load and validate input JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    for field in ["project", "functional_requirements", "non_functional_requirements"]:
        if field not in data:
            raise ValueError(f"Missing required field: '{field}'")
    logger.info(f"Loaded: {data['project']} | {len(data['functional_requirements'])} FRs, "
                f"{len(data['non_functional_requirements'])} NFRs")
    return data


def generate_and_rank(input_file: str | Path, models: list[str] = None,
                      candidates_per_model: int = None, ws=None) -> dict:
    """
    Phase 1: Generate candidates, evaluate, rank, and wait for human selection.
    """
    models = models or MODELS
    candidates_per_model = candidates_per_model or CANDIDATES_PER_MODEL
    import uuid
    run_id = str(uuid.uuid4())[:8]

    def notify(step, message):
        if ws:
            ws.send_json({"step": step, "message": message, "run_id": run_id})

    logger.info(f"Starting Phase 1 pipeline... Run ID: {run_id}")
    requirements = load_input(input_file)
    project = requirements.get("project", "Unknown")
    
    # Init run in DB
    # We use create_run instead of insert_run since create_run is what db.py uses for initial creation
    try:
        from storage.db import insert_run
        insert_run(run_id, project, json.dumps(requirements))
    except ImportError:
        create_run(project, requirements, run_id=run_id)

    notify("init", f"Loaded: {project}")

    # Check models
    notify("models", "Checking model availability...")
    availability = check_models_available(models)
    available_models = [m for m in models if availability.get(m, False)]
    if not available_models:
        raise RuntimeError("No LLM models available.")

    all_candidates = []

    # Generate
    notify("generation", "Generating architecture candidates...")
    candidates = generate_all(build_architecture_prompt(requirements), models=available_models, candidates_per_model=candidates_per_model)

    for c in candidates:
        if not c.success:
            continue
        try:
            arch = parse_architecture(c.raw_text)
            scores = evaluate_architecture(arch, requirements)
            all_candidates.append({
                "model": c.model,
                "candidate_num": c.candidate_num,
                "raw_text": c.raw_text,
                "architecture": arch,
                "scores": scores,
            })
        except ParseError as e:
            logger.warning(f"Skipping unparseable candidate: {e}")

    if not all_candidates:
        update_run(run_id, status="failed")
        raise RuntimeError("No valid architecture candidates produced")

    # Rank
    notify("rank", "Ranking candidates...")
    ranked = rank_candidates(all_candidates)

    # Log to DB and set to pending_selection
    for c in ranked:
        insert_candidate(run_id, c["model"], c["candidate_num"],
                         c["architecture"], c["scores"], c["rank"])
    
    update_run(run_id, status="pending_selection", total_candidates=len(ranked))
    
    # Generate the group radar chart for the UI to use in Phase 2
    radar_path = RESULTS_DIR / "radar_chart.png"
    generate_radar_chart(ranked, str(radar_path), f"{project} — Tradeoff Comparison")

    notify("done", "Phase 1 complete. Pending human selection.")
    logger.info(f"Phase 1 complete! Pending selection for Run ID: {run_id}")

    return {
        "run_id": run_id,
        "ranked_candidates": ranked,
        "radar": str(radar_path)
    }


def elaborate_winner(run_id: str, selected_candidate: dict, input_file: str | Path, ws=None) -> dict:
    """
    Phase 2: Elaborate the user-selected winner.
    """
    def notify(step, message):
        if ws:
            ws.send_json({"step": step, "message": message, "run_id": run_id})

    logger.info(f"Starting Phase 2 elaboration for Run ID: {run_id}")
    requirements = load_input(input_file)
    project = requirements.get("project", "Unknown")

    notify("output", "Generating final artifacts...")

    winner_path = RESULTS_DIR / "winner.json"
    with open(winner_path, "w", encoding="utf-8") as f:
        json.dump({"run_id": run_id, "model": selected_candidate["model"],
                    "scores": selected_candidate["scores"], "architecture": selected_candidate["architecture"]}, f, indent=2)

    # Note: generate_report technically needs the ranked list, but we can just pass the winner as a single-item list
    # or recreate it. For now, we pass the winner.
    report_path = RESULTS_DIR / "evaluation_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(generate_report([selected_candidate], requirements, run_id))

    puml_path = RESULTS_DIR / "diagram.puml"
    with open(puml_path, "w", encoding="utf-8") as f:
        f.write(generate_plantuml(selected_candidate["architecture"], project))

    mmd_path = RESULTS_DIR / "diagram.mmd"
    with open(mmd_path, "w", encoding="utf-8") as f:
        f.write(generate_mermaid(selected_candidate["architecture"], project))

    update_run(run_id, status="completed",
               winner_model=selected_candidate["model"], winner_cas=selected_candidate["scores"]["CAS"])

    notify("done", "Elaboration complete!")
    logger.info(f"✅ Elaboration complete! Run ID: {run_id}")

    return {
        "run_id": run_id, "winner": selected_candidate,
        "outputs": {"winner_json": str(winner_path), "report": str(report_path),
                     "plantuml": str(puml_path), "mermaid": str(mmd_path)},
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="HLA Agent ATAM Pipeline")
    parser.add_argument("input", nargs="?",
                        default=str(INPUT_DIR / "sample_food_delivery.json"))
    parser.add_argument("--models", nargs="+", default=None)
    parser.add_argument("--candidates", type=int, default=None)
    args = parser.parse_args()

    print(f"\n{'='*50}")
    print("PHASE 1: GENERATE & EVALUATE")
    print(f"{'='*50}")
    phase1 = generate_and_rank(args.input, args.models, args.candidates)
    
    print(f"\nCandidates ready for ATAM Tradeoff Analysis: {len(phase1['ranked_candidates'])}")
    for c in phase1["ranked_candidates"]:
        print(f"[{c['rank']}] {c['model']} (CAS: {c['scores']['CAS']:.4f})")
        
    print(f"\n{'='*50}")
    print("PHASE 2: ELABORATION")
    print(f"{'='*50}")
    print("Auto-selecting the highest ranked candidate for CLI execution...")
    
    selected = phase1['ranked_candidates'][0]
    result = elaborate_winner(phase1['run_id'], selected, args.input)

    print(f"\nRUN COMPLETE — ID: {result['run_id']}")
    print(f"Winner: {result['winner']['model']} (CAS={result['winner']['scores']['CAS']:.4f})")
    print(f"Outputs generated in {RESULTS_DIR}")
    print(f"{'='*50}")
