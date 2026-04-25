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


def run_pipeline(input_path: str, models=None, candidates_per_model=None,
                 progress_callback=None) -> dict:
    """Execute the full HLA Agent pipeline."""
    models = models or MODELS
    candidates_per_model = candidates_per_model or CANDIDATES_PER_MODEL

    def notify(step, msg, data=None):
        if progress_callback:
            progress_callback(step, msg, data)

    # Step 1: Load Input
    notify("load", "Loading requirements...")
    requirements = load_input(input_path)
    project = requirements["project"]

    # Step 2: Check Models
    notify("models", "Checking model availability...")
    availability = check_models_available(models)
    available_models = [m for m in models if availability.get(m, False)]
    if not available_models:
        raise RuntimeError(
            f"No LLM models available for provider '{LLM_PROVIDER}'. "
            f"Check your API key in .env or switch provider."
        )
    logger.info(f"Available models: {available_models}")

    # Step 3: Create DB Run
    run_id = create_run(project, requirements)
    notify("init", f"Run ID: {run_id}")

    # Step 4: Build Prompt
    notify("prompt", "Building structured prompt...")
    prompt = build_architecture_prompt(requirements)

    # Step 5: Generate Architectures
    notify("generate", "Generating architectures from LLMs...")
    gen_results = generate_all(prompt, models=available_models,
                               candidates_per_model=candidates_per_model)

    # Step 6: Parse & Evaluate with Regenerative Loop
    notify("evaluate", "Parsing and evaluating candidates...")
    all_candidates = []

    for gen in gen_results:
        if not gen.success:
            continue
        try:
            architecture = parse_architecture(gen.raw_text)
        except ParseError as e:
            logger.warning(f"Parse failed for {gen.model} #{gen.candidate_num}: {e}")
            continue

        scores = evaluate_architecture(architecture, requirements)
        candidate = {
            "model": gen.model,
            "candidate_num": gen.candidate_num,
            "architecture": architecture,
            "scores": scores,
            "generation_time_ms": gen.duration_ms,
        }

        # Regenerative loop if below threshold
        if scores["CAS"] < THRESHOLDS["CAS"]:
            feedback = build_feedback_from_scores(scores, THRESHOLDS)
            for attempt in range(MAX_REGENERATION_LOOPS):
                regen = regenerate_single(gen.model, prompt, gen.candidate_num, feedback)
                if not regen.success:
                    break
                try:
                    regen_arch = parse_architecture(regen.raw_text)
                    regen_scores = evaluate_architecture(regen_arch, requirements)
                    if regen_scores["CAS"] > scores["CAS"]:
                        candidate["architecture"] = regen_arch
                        candidate["scores"] = regen_scores
                        scores = regen_scores
                        if scores["CAS"] >= THRESHOLDS["CAS"]:
                            break
                except ParseError:
                    pass

        all_candidates.append(candidate)

    if not all_candidates:
        update_run(run_id, status="failed")
        raise RuntimeError("No valid architecture candidates produced")

    # Step 7: Rank
    notify("rank", "Ranking candidates...")
    ranked = rank_candidates(all_candidates)
    winner = ranked[0]

    # Step 8: Generate Outputs
    notify("output", "Generating outputs...")

    winner_path = RESULTS_DIR / "winner.json"
    with open(winner_path, "w", encoding="utf-8") as f:
        json.dump({"run_id": run_id, "model": winner["model"],
                    "scores": winner["scores"], "architecture": winner["architecture"]}, f, indent=2)

    report_path = RESULTS_DIR / "evaluation_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(generate_report(ranked, requirements, run_id))

    puml_path = RESULTS_DIR / "diagram.puml"
    with open(puml_path, "w", encoding="utf-8") as f:
        f.write(generate_plantuml(winner["architecture"], project))

    mmd_path = RESULTS_DIR / "diagram.mmd"
    with open(mmd_path, "w", encoding="utf-8") as f:
        f.write(generate_mermaid(winner["architecture"], project))

    radar_path = RESULTS_DIR / "radar_chart.png"
    generate_radar_chart(ranked, str(radar_path), f"{project} — Radar")

    # Step 9: Log to DB
    for c in ranked:
        insert_candidate(run_id, c["model"], c["candidate_num"],
                         c["architecture"], c["scores"], c["rank"])
    update_run(run_id, status="completed", total_candidates=len(ranked),
               winner_model=winner["model"], winner_cas=winner["scores"]["CAS"])

    notify("done", "Pipeline complete!")
    logger.info(f"✅ Pipeline complete! Run ID: {run_id}")

    return {
        "run_id": run_id, "ranked_candidates": ranked, "winner": winner,
        "outputs": {"winner_json": str(winner_path), "report": str(report_path),
                     "plantuml": str(puml_path), "mermaid": str(mmd_path),
                     "radar": str(radar_path)},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HLA Agent Pipeline")
    parser.add_argument("input", nargs="?",
                        default=str(INPUT_DIR / "sample_food_delivery.json"))
    parser.add_argument("--models", nargs="+", default=None)
    parser.add_argument("--candidates", type=int, default=None)
    args = parser.parse_args()

    result = run_pipeline(args.input, args.models, args.candidates)
    print(f"\n{'='*50}")
    print(f"RUN COMPLETE — ID: {result['run_id']}")
    print(f"Winner: {result['winner']['model']} (CAS={result['winner']['scores']['CAS']:.4f})")
    print(f"{'='*50}")
