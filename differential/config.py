"""Central configuration: repository paths and environment switches.

The project's own Claude API calls read the key from ``DIFFERENTIAL_API_KEY`` only.
``ANTHROPIC_API_KEY`` is deliberately never consulted, and the key is never logged.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Worker processes parallelise across hypotheses; keep BLAS single-threaded inside
# each so they do not oversubscribe the CPU.
for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

REPO_ROOT = Path(__file__).resolve().parent.parent
CIRCUITS_DIR = REPO_ROOT / "circuits"
DATA_DIR = REPO_ROOT / "data"
SIM_DIR = DATA_DIR / "sim"
EVAL_DATA_DIR = DATA_DIR / "eval"
MODELS_DIR = DATA_DIR / "models"
LLM_CACHE_DIR = DATA_DIR / "llm_cache"
SESSIONS_DIR = DATA_DIR / "sessions"
METER_DIR = DATA_DIR / "meter_photos"
RESULTS_DIR = REPO_ROOT / "results"
FIGURES_DIR = RESULTS_DIR / "figures"
TABLES_DIR = RESULTS_DIR / "tables"

DEFAULT_MODEL = "claude-sonnet-5-5"


@dataclass(frozen=True)
class LLMSettings:
    """Settings for the live Claude path. ``api_key`` is None in offline mode."""

    api_key: str | None
    model: str

    @property
    def live(self) -> bool:
        return bool(self.api_key)


def llm_settings() -> LLMSettings:
    key = os.environ.get("DIFFERENTIAL_API_KEY") or None
    model = os.environ.get("DIFFERENTIAL_MODEL", DEFAULT_MODEL)
    return LLMSettings(api_key=key, model=model)


def app_mode() -> str:
    """Demo mode: 'offline' (default without a key), 'live', or 'replay'."""
    mode = os.environ.get("DIFFERENTIAL_MODE")
    if mode:
        return mode
    return "live" if llm_settings().live else "offline"


def n_workers() -> int:
    env = os.environ.get("DIFFERENTIAL_WORKERS")
    if env:
        return max(1, int(env))
    return max(1, os.cpu_count() or 1)
