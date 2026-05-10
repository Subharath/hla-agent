"""
HLA Agent — SQLite Storage
Logs all runs, candidates, and scores for historical comparison.
"""

import sqlite3
import json
import uuid
import logging
from datetime import datetime
from config import DB_PATH

logger = logging.getLogger(__name__)


def _get_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Create database tables if they don't exist."""
    conn = _get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            project TEXT NOT NULL,
            input_json TEXT,
            status TEXT DEFAULT 'running',
            total_candidates INTEGER DEFAULT 0,
            winner_model TEXT,
            winner_cas REAL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            model TEXT NOT NULL,
            candidate_num INTEGER NOT NULL,
            architecture_style TEXT,
            architecture_json TEXT,
            rcr REAL, nas REAL, smi REAL, lscs REAL, sci REAL,
            cas REAL,
            verdict TEXT,
            rank INTEGER,
            FOREIGN KEY (run_id) REFERENCES runs(run_id)
        )
    """)

    conn.commit()
    conn.close()
    logger.info(f"Database initialized at {DB_PATH}")


def create_run(project: str, input_json: dict, run_id: str = None) -> str:
    """Create a new run entry. Returns run_id."""
    run_id = run_id or str(uuid.uuid4())[:8]
    conn = _get_connection()
    conn.execute(
        "INSERT INTO runs (run_id, timestamp, project, input_json) VALUES (?, ?, ?, ?)",
        (run_id, datetime.now().isoformat(), project, json.dumps(input_json))
    )
    conn.commit()
    conn.close()
    return run_id


def update_run(run_id: str, **kwargs):
    """Update run fields."""
    conn = _get_connection()
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [run_id]
    conn.execute(f"UPDATE runs SET {sets} WHERE run_id = ?", vals)
    conn.commit()
    conn.close()


def insert_candidate(run_id: str, model: str, candidate_num: int,
                     architecture: dict, scores: dict, rank: int):
    """Insert a scored candidate into the database. Returns the row ID."""
    conn = _get_connection()
    cursor = conn.execute("""
        INSERT INTO candidates
        (run_id, model, candidate_num, architecture_style, architecture_json,
         rcr, nas, smi, lscs, sci, cas, verdict, rank)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_id, model, candidate_num,
        architecture.get("architecture_style", ""),
        json.dumps(architecture),
        scores.get("RCR", 0), scores.get("NAS", 0), scores.get("SMI", 0),
        scores.get("LSCS", 0), scores.get("SCI", 0), scores.get("CAS", 0),
        scores.get("verdict", ""), rank,
    ))
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def get_run(run_id: str) -> dict:
    """Get a single run by ID."""
    conn = _get_connection()
    row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_candidates(run_id: str) -> list[dict]:
    """Get all candidates for a run, sorted by rank."""
    conn = _get_connection()
    rows = conn.execute(
        "SELECT * FROM candidates WHERE run_id = ? ORDER BY rank", (run_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_runs() -> list[dict]:
    """Get all runs, most recent first."""
    conn = _get_connection()
    rows = conn.execute(
        "SELECT * FROM runs ORDER BY timestamp DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_candidate(candidate_id: int) -> dict:
    """Get a single candidate by its ID."""
    conn = _get_connection()
    row = conn.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


# Initialize DB on import
init_db()
