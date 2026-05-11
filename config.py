"""
HLA Agent — Central Configuration
All constants, thresholds, weights, and mappings live here.
Nothing is hardcoded anywhere else in the project.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if present
load_dotenv(Path(__file__).parent / ".env")

# ──────────────────────────────────────────────
# PATHS
# ──────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
INPUT_DIR = BASE_DIR / "input"
RESULTS_DIR = BASE_DIR / "results"
WEB_DIR = BASE_DIR / "web"
DB_PATH = RESULTS_DIR / "results.db"

# Ensure results directory exists
RESULTS_DIR.mkdir(exist_ok=True)

# ──────────────────────────────────────────────
# LLM PROVIDER CONFIGURATION
# ──────────────────────────────────────────────
# Provider: "groq", "deepseek", "gemini", "ollama"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")

# API Keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Ollama (fallback for local GPU users)
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

# Models per provider
PROVIDER_MODELS = {
    "groq": ["llama-3.3-70b-versatile"],
    "deepseek": ["deepseek-v4-flash", "deepseek-v4-pro"],
    "gemini": ["gemini-2.0-flash"],
    "ollama": ["llama3.1", "mistral", "qwen3"],
}

# Active models (Cross-provider comparison)
# Using local Ollama for testing: llama3.1, mistral, qwen3
MODELS = ["llama3.1", "mistral", "qwen3"]

# Number of architecture candidates each model generates
CANDIDATES_PER_MODEL = 2

# Generation parameters (provider-agnostic)
GENERATION_OPTIONS = {
    "temperature": 0.1,
    "max_tokens": 4000,
    "top_p": 0.2,
    "seed": 42,
}

# Retry configuration
MAX_GENERATION_RETRIES = 3
MAX_REGENERATION_LOOPS = 0  # Disabled: using Human-in-the-Loop manual iteration

# ──────────────────────────────────────────────
# METRIC THRESHOLDS (minimum acceptable scores)
# ──────────────────────────────────────────────
PHASE1_THRESHOLDS = {
    "RCR":  0.80,   # Requirement Coverage Ratio
    "NAS":  0.75,   # NFR Alignment Score
    "CAS":  0.75,   # Composite Architecture Score (acceptance gate)
}

PHASE2_THRESHOLDS = {
    "SMI":  0.75,   # Structural Modularity Index
    "LSCS": 0.90,   # Layer Separation Consistency Score
    "SCI":  0.80,   # Structural Clarity Index
}

THRESHOLDS = {**PHASE1_THRESHOLDS, **PHASE2_THRESHOLDS}

# ──────────────────────────────────────────────
# METRIC WEIGHTS (must sum to 1.0)
# ──────────────────────────────────────────────
PHASE1_WEIGHTS = {
    "RCR":  0.50,
    "NAS":  0.50,
}

PHASE2_WEIGHTS = {
    "SMI":  0.40,
    "LSCS": 0.30,
    "SCI":  0.30,
}

WEIGHTS = {
    "RCR":  0.25,
    "NAS":  0.25,
    "SMI":  0.20,
    "LSCS": 0.15,
    "SCI":  0.15,
}

# Verify weights sum to 1.0
assert abs(sum(PHASE1_WEIGHTS.values()) - 1.0) < 1e-9, "Phase 1 weights must sum to 1.0"
assert abs(sum(PHASE2_WEIGHTS.values()) - 1.0) < 1e-9, "Phase 2 weights must sum to 1.0"
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "Metric weights must sum to 1.0"

# ──────────────────────────────────────────────
# ARCHITECTURE STYLES
# ──────────────────────────────────────────────
ARCHITECTURE_STYLES = [
    "Layered Architecture",
    "Event-Driven Architecture",
    "Microkernel Architecture",
    "Microservices Architecture",
    "Space-Based Architecture",
]

# ──────────────────────────────────────────────
# NFR EVIDENCE MAP (for NAS metric)
# Maps NFR types to STYLE-NEUTRAL keywords that
# indicate architectural support for that quality.
# ──────────────────────────────────────────────
NFR_EVIDENCE_MAP = {
    "scalability": [
        "load balancer", "scaling", "horizontal", "vertical scaling",
        "cluster", "partition", "shard", "auto-scale", "elastic",
        "replicate", "cdn", "stateless", "connection pool",
        "read replica", "cache", "async", "queue",
    ],
    "performance": [
        "cache", "redis", "cdn", "async", "queue", "batch",
        "index", "in-memory", "optimiz", "pool", "buffer",
        "compress", "lazy load", "pagination", "connection pool",
    ],
    "security": [
        "auth", "jwt", "encryption", "tls", "ssl", "oauth",
        "rbac", "firewall", "token", "certificate", "hash",
        "sanitiz", "validate", "permission", "access control",
        "audit", "logging", "input validation",
    ],
    "availability": [
        "replica", "failover", "redundant", "backup", "health check",
        "circuit breaker", "retry", "standby", "disaster recovery",
        "high availability", "monitoring", "watchdog",
        "graceful degradation", "hot standby", "load balancer",
    ],
    "maintainability": [
        "modular", "plugin", "interface", "abstraction", "factory",
        "repository pattern", "dependency injection", "loosely coupled",
        "separation of concerns", "clean code", "adapter",
        "port", "hexagonal", "layered",
    ],
    "reliability": [
        "retry", "circuit breaker", "graceful degradation", "monitoring",
        "alerting", "logging", "dead letter", "idempoten", "rollback",
        "transaction", "saga", "backup", "validation",
        "data integrity", "consistency",
    ],
}

# ──────────────────────────────────────────────
# SCI — Valid Component Suffixes
# ──────────────────────────────────────────────
VALID_COMPONENT_SUFFIXES = [
    "Service", "Controller", "Repository", "Gateway", "Manager",
    "Handler", "Engine", "Producer", "Consumer", "Client",
    "Proxy", "Adapter", "Factory", "Provider", "Middleware",
    "Router", "Dispatcher", "Scheduler", "Monitor", "Worker",
    "Bus", "Broker", "Registry", "Store", "Cache",
    "Balancer", "Queue", "Logger", "Validator", "Processor",
    "Interactor", "Port", "UseCase",
]

# Minimum words in responsibility description for SCI
MIN_RESPONSIBILITY_WORDS = 5

# ──────────────────────────────────────────────
# LAYER ORDERING (for LSCS metric)
# Higher number = lower in the stack
# ──────────────────────────────────────────────
DEFAULT_LAYER_ORDER = {
    "presentation":     1,
    "ui":               1,
    "frontend":         1,
    "client":           1,
    "api gateway":      2,
    "gateway":          2,
    "api":              2,
    "application":      3,
    "business logic":   3,
    "business":         3,
    "service":          3,
    "use case":         3,
    "domain":           4,
    "data access":      5,
    "persistence":      5,
    "database":         6,
    "infrastructure":   6,
    "external":         7,
    "integration":      7,
    "messaging":        4,
    "event bus":        4,
    "ports":            3,
    "adapters":         5,
}

# ──────────────────────────────────────────────
# CAS VERDICT RANGES
# ──────────────────────────────────────────────
CAS_ACCEPTED = 0.75
CAS_MARGINAL = 0.60
# Below CAS_MARGINAL = Poor (must regenerate)

