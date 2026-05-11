"""
HLA Agent — FastAPI Web Server
REST API + WebSocket for the web dashboard.
"""

import sys
import json
import asyncio
import logging
from pathlib import Path
from contextlib import asynccontextmanager

sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import csv
import uvicorn

from config import INPUT_DIR, RESULTS_DIR, WEB_DIR, MODELS, LLM_PROVIDER, PROVIDER_MODELS
from storage.db import get_all_runs, get_run, get_candidates
from generation.generator import check_models_available
from providers import get_provider_name

logger = logging.getLogger("HLA-Server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("HLA Agent Server starting...")
    RESULTS_DIR.mkdir(exist_ok=True)
    yield
    logger.info("HLA Agent Server shutting down...")


app = FastAPI(title="HLA Agent", version="1.0.0", lifespan=lifespan)

# Serve static web files
app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


# ─── Pages ─────────────────────────────────────────
@app.get("/")
async def serve_dashboard():
    return FileResponse(str(WEB_DIR / "index.html"))


# ─── API Endpoints ─────────────────────────────────
@app.get("/api/health")
async def health():
    availability = check_models_available()
    provider = get_provider_name()
    return {
        "status": "ok",
        "provider": provider,
        "models": availability,
        "configured_models": MODELS,
        "all_providers": list(PROVIDER_MODELS.keys()),
    }


@app.get("/api/samples")
async def list_samples():
    samples = []
    for f in INPUT_DIR.glob("*.json"):
        with open(f, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        samples.append({"filename": f.name, "project": data.get("project", f.stem),
                         "frs": len(data.get("functional_requirements", [])),
                         "nfrs": len(data.get("non_functional_requirements", []))})
    return samples


@app.get("/api/samples/{filename}")
async def get_sample(filename: str):
    path = INPUT_DIR / filename
    if not path.exists():
        raise HTTPException(404, "Sample not found")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/history")
async def history():
    return get_all_runs()


@app.get("/api/results/{run_id}")
async def results(run_id: str):
    run = get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    candidates = get_candidates(run_id)
    return {"run": run, "candidates": candidates}


@app.get("/api/results/{run_id}/report")
async def get_report(run_id: str):
    path = RESULTS_DIR / "evaluation_report.md"
    if not path.exists():
        raise HTTPException(404, "Report not found")
    return FileResponse(str(path), media_type="text/markdown")


@app.get("/api/results/{run_id}/radar")
async def get_radar(run_id: str):
    path = RESULTS_DIR / "radar_chart.png"
    if not path.exists():
        raise HTTPException(404, "Radar chart not found")
    return FileResponse(str(path), media_type="image/png")


@app.get("/api/results/{run_id}/diagram/{dtype}")
async def get_diagram(run_id: str, dtype: str):
    if dtype == "plantuml":
        path = RESULTS_DIR / "diagram.puml"
    elif dtype == "mermaid":
        path = RESULTS_DIR / "diagram.mmd"
    else:
        raise HTTPException(400, "Invalid diagram type. Use 'plantuml' or 'mermaid'")
    if not path.exists():
        raise HTTPException(404, "Diagram not found")
    with open(path, "r", encoding="utf-8") as f:
        return {"type": dtype, "content": f.read()}


@app.get("/api/results/{run_id}/winner")
async def get_winner(run_id: str):
    path = RESULTS_DIR / "winner.json"
    if not path.exists():
        raise HTTPException(404, "Winner not found")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.post("/api/runs/{run_id}/export_evidence")
async def export_evidence(run_id: str):
    """Export per-candidate NFR evidence and raw LLM text as CSV for auditing."""
    run = get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")

    candidates = get_candidates(run_id)
    if not candidates:
        raise HTTPException(404, "No candidates found for run")

    RESULTS_DIR.mkdir(exist_ok=True)
    out_path = RESULTS_DIR / f"evidence_{run_id}.csv"

    with open(out_path, "w", newline='', encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["candidate_id", "model", "candidate_num", "nfr_id", "nfr_type", "nfr_target", "nfr_score", "nfr_reasoning", "raw_text"])

        for c in candidates:
            cid = c.get("id") or ""
            model = c.get("model", "")
            cand_num = c.get("candidate_num", "")
            scores = c.get("scores", {}) or {}
            alignment_map = scores.get("alignment_map", {}) or {}
            llm = c.get("llm", {}) or {}
            raw = llm.get("raw_text", "")

            # If alignment_map empty, write a single row per candidate
            if not alignment_map:
                writer.writerow([cid, model, cand_num, "", "", "", "", "", raw.replace('\n', ' ')])
            else:
                for nfr_id, info in alignment_map.items():
                    writer.writerow([
                        cid, model, cand_num, nfr_id, info.get("type", ""), info.get("target", ""), info.get("score", ""), info.get("reasoning", "").replace('\n',' '), raw.replace('\n', ' ')
                    ])

    return FileResponse(str(out_path), media_type="text/csv")


# ─── WebSocket for Pipeline Execution ──────────────
@app.websocket("/ws/pipeline")
async def websocket_pipeline(ws: WebSocket):
    await ws.accept()
    try:
        data = await ws.receive_json()
        requirements = data.get("requirements")
        selected_models = data.get("models", MODELS)

        if not requirements:
            await ws.send_json({"type": "error", "message": "No requirements provided"})
            return

        # Save temp input
        temp_path = RESULTS_DIR / "_temp_input.json"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(requirements, f)

        # Run pipeline Phase 1 in thread to not block
        from main import generate_and_rank

        await ws.send_json({"type": "status", "step": "start", "message": "Phase 1 starting..."})

        # Run in executor
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None, lambda: generate_and_rank(str(temp_path), models=selected_models)
            )

            # Build response
            ranked_data = []
            for c in result["ranked_candidates"]:
                ranked_data.append({
                    "rank": c["rank"], "model": c["model"],
                    "candidate_num": c["candidate_num"],
                    "scores": c["scores"],
                    "architecture": c["architecture"],
                    "llm": c.get("llm", {}),
                    "id": c.get("id", None) # if we need db id later
                })

            await ws.send_json({
                "type": "phase1_complete",
                "run_id": result["run_id"],
                "candidates": ranked_data,
            })
        except Exception as e:
            await ws.send_json({"type": "error", "message": str(e)})

    except WebSocketDisconnect:
        logger.info("Client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")


from pydantic import BaseModel

class SelectionRequest(BaseModel):
    """User selection of a candidate for Phase 2 elaboration."""
    model: str
    architecture: dict
    scores: dict
    input_file_path: str = str(RESULTS_DIR / "_temp_input.json")

class RegenerateRequest(BaseModel):
    model: str
    candidate_num: int
    error: str

@app.post("/api/runs/{run_id}/regenerate")
async def regenerate_candidate_endpoint(run_id: str, req: RegenerateRequest):
    from generation.generator import regenerate_single
    from prompt.builder import build_architecture_prompt
    from main import parse_architecture, evaluate_architecture, ParseError
    
    path = RESULTS_DIR / "_temp_input.json"
    with open(path, "r", encoding="utf-8") as f:
        requirements = json.load(f)
        
    prompt = build_architecture_prompt(requirements)
    
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, lambda: regenerate_single(req.model, prompt, req.candidate_num, req.error)
    )
    
    if not result.success:
        return {
            "success": False,
            "candidate": {
                "model": req.model, "candidate_num": req.candidate_num, "rank": -1,
                "error": result.error or "Regeneration failed",
                    "scores": {
                        "PHASE1_CAS": 0,
                        "CAS": 0,
                        "RCR": 0,
                        "NAS": 0,
                        "SMI": 0,
                        "LSCS": 0,
                        "SCI": 0,
                        "phase1_verdict": "Failed",
                        "verdict": "Failed"
                    },
                    "llm": {
                        "provider": getattr(result, "provider_name", ""),
                        "duration_ms": result.duration_ms,
                        "attempts": getattr(result, "attempts", []),
                        "raw_text": result.raw_text,
                    },
                "architecture": {"architecture_style": "Failed", "components": []}
            }
        }
        
    try:
        arch = parse_architecture(result.raw_text)
        scores = evaluate_architecture(arch, requirements)
        return {
            "success": True,
            "candidate": {
                "model": req.model, "candidate_num": req.candidate_num, "rank": -1,
                "architecture": arch,
                "scores": scores,
                    "llm": {
                        "provider": getattr(result, "provider_name", ""),
                        "duration_ms": result.duration_ms,
                        "attempts": getattr(result, "attempts", []),
                        "raw_text": result.raw_text,
                    },
                "error": None
            }
        }
    except ParseError as e:
        return {
            "success": False,
            "candidate": {
                "model": req.model, "candidate_num": req.candidate_num, "rank": -1,
                "error": f"Parse Error: {e}",
                    "scores": {
                        "PHASE1_CAS": 0,
                        "CAS": 0,
                        "RCR": 0,
                        "NAS": 0,
                        "SMI": 0,
                        "LSCS": 0,
                        "SCI": 0,
                        "phase1_verdict": "Parse Failed",
                        "verdict": "Parse Failed"
                    },
                    "llm": {
                        "provider": getattr(result, "provider_name", ""),
                        "duration_ms": result.duration_ms,
                        "attempts": getattr(result, "attempts", []),
                        "raw_text": result.raw_text,
                    },
                "architecture": {"architecture_style": "Unparseable", "components": []}
            }
        }


@app.post("/api/runs/{run_id}/select")
async def select_winner(run_id: str, req: SelectionRequest):
    """Phase 2: Elaborate the selected winner candidate."""
    from main import elaborate_winner
    
    # Build candidate object from request
    candidate = {
        "model": req.model,
        "architecture": req.architecture,
        "scores": req.scores,
    }
    
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: elaborate_winner(run_id, candidate, req.input_file_path)
        )
        return {
            "status": "success",
            "run_id": run_id,
            "outputs": result["outputs"],
            "winner": {
                "model": result["winner"]["model"],
                "scores": result["winner"]["scores"],
                "architecture": result["winner"]["architecture"]
            }
        }
    except Exception as e:
        logger.error(f"Elaboration failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
