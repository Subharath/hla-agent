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

        # Run pipeline in thread to not block
        from main import run_pipeline

        def progress_cb(step, msg, extra=None):
            # Can't await in sync callback, so we use a simple approach
            pass

        await ws.send_json({"type": "status", "step": "start", "message": "Pipeline starting..."})

        # Run in executor
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None, lambda: run_pipeline(str(temp_path), models=selected_models)
            )

            # Build response
            ranked_data = []
            for c in result["ranked_candidates"]:
                ranked_data.append({
                    "rank": c["rank"], "model": c["model"],
                    "candidate_num": c["candidate_num"],
                    "scores": c["scores"],
                    "architecture": c["architecture"],
                })

            await ws.send_json({
                "type": "complete",
                "run_id": result["run_id"],
                "candidates": ranked_data,
                "winner": {
                    "model": result["winner"]["model"],
                    "scores": result["winner"]["scores"],
                    "architecture": result["winner"]["architecture"],
                },
                "outputs": result["outputs"],
            })
        except Exception as e:
            await ws.send_json({"type": "error", "message": str(e)})

    except WebSocketDisconnect:
        logger.info("Client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
