"""Run the preregistered four-condition non-spatial ablation experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

for variable in (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
):
    os.environ.setdefault(variable, "1")

import numpy as np
import pandas as pd


ANALYSIS_STATUS = "formal_nonspatial_ablation_v1"
EXPERIMENT_DIR = Path(__file__).resolve().parent
ORIGINAL_ROOT = EXPERIMENT_DIR.parent
PROJECT_SRC = ORIGINAL_ROOT / "src" / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

from reverse_black_box_abm.model import (  # noqa: E402
    ReverseBlackBoxSimulation,
    SimulationConfig,
)


ALPHAS = tuple(round(index * 0.05, 2) for index in range(21))
SEEDS = tuple(range(73000, 73050))
CONDITIONS = (
    {
        "condition_id": "full",
        "condition_order": 0,
        "condition_label": "Full model",
        "removed_mechanism": "none",
        "emotion_advantage_enabled": True,
        "preference_drift_rate": 0.03,
        "response_strength": 0.70,
    },
    {
        "condition_id": "no_emotion",
        "condition_order": 1,
        "condition_label": "No emotion advantage",
        "removed_mechanism": "emotion_advantage",
        "emotion_advantage_enabled": False,
        "preference_drift_rate": 0.03,
        "response_strength": 0.70,
    },
    {
        "condition_id": "no_drift",
        "condition_order": 2,
        "condition_label": "No preference drift",
        "removed_mechanism": "preference_drift",
        "emotion_advantage_enabled": True,
        "preference_drift_rate": 0.0,
        "response_strength": 0.70,
    },
    {
        "condition_id": "no_response",
        "condition_order": 3,
        "condition_label": "No effective response",
        "removed_mechanism": "government_response",
        "emotion_advantage_enabled": True,
        "preference_drift_rate": 0.03,
        "response_strength": 1.0,
    },
)


@dataclass(frozen=True)
class UnifiedNonSpatialConfig(SimulationConfig):
    """Original non-spatial configuration with an explicit emotion switch."""

    emotion_advantage_enabled: bool = True


class UnifiedNonSpatialSimulation(ReverseBlackBoxSimulation):
    """One auditable model class for all four experimental conditions."""

    config: UnifiedNonSpatialConfig

    def _sample_spontaneous_emotion(self, topic: int) -> float:
        if (
            self.config.emotion_advantage_enabled
            and topic in self.config.off_agenda_topic_indices
        ):
            return float(self.rng.beta(4.0, 2.0))
        return float(self.rng.beta(2.0, 3.0))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _design_payload() -> dict[str, Any]:
    baseline = UnifiedNonSpatialConfig(alpha=0.5, seed=SEEDS[0])
    forbidden_spatial_fields = {
        "grid_size",
        "vision_radius",
        "diffusion_probability",
        "max_diffusions_per_step",
    }
    present = forbidden_spatial_fields.intersection(asdict(baseline))
    if present:
        raise RuntimeError(f"spatial fields unexpectedly present: {sorted(present)}")
    return {
        "analysis_status": ANALYSIS_STATUS,
        "model_family": "original_nonspatial_global_information_pool",
        "alphas": list(ALPHAS),
        "seeds": list(SEEDS),
        "replicates_per_cell": len(SEEDS),
        "conditions": list(CONDITIONS),
        "baseline_config": asdict(baseline),
        "steady_state_window": 100,
        "expected_rows": len(ALPHAS) * len(SEEDS) * len(CONDITIONS),
    }


DESIGN = _design_payload()
RUN_SIGNATURE = _json_hash(DESIGN)
CONDITION_BY_ID = {item["condition_id"]: item for item in CONDITIONS}


def _configuration_for(condition_id: str, alpha: float, seed: int) -> UnifiedNonSpatialConfig:
    specification = CONDITION_BY_ID[condition_id]
    return UnifiedNonSpatialConfig(
        alpha=float(alpha),
        seed=int(seed),
        preference_drift_rate=float(specification["preference_drift_rate"]),
        response_strength=float(specification["response_strength"]),
        emotion_advantage_enabled=bool(
            specification["emotion_advantage_enabled"]
        ),
    )


def _run_task(task: tuple[str, float, int, int]) -> dict[str, Any]:
    condition_id, alpha, replicate, seed = task
    specification = CONDITION_BY_ID[condition_id]
    config = _configuration_for(condition_id, alpha, seed)
    started = time.perf_counter()
    result = UnifiedNonSpatialSimulation(config).run()
    row: dict[str, Any] = {
        "analysis_status": ANALYSIS_STATUS,
        "run_signature": RUN_SIGNATURE,
        "condition_id": condition_id,
        "condition_order": specification["condition_order"],
        "condition_label": specification["condition_label"],
        "removed_mechanism": specification["removed_mechanism"],
        "emotion_advantage_enabled": specification[
            "emotion_advantage_enabled"
        ],
        "preference_drift_rate": specification["preference_drift_rate"],
        "response_strength": specification["response_strength"],
        "replicate": int(replicate),
        "seed": int(seed),
        "alpha": float(alpha),
        "configuration_sha256": _json_hash(asdict(config)),
    }
    for key, value in result.summary.items():
        if key not in {"alpha", "seed"}:
            row[key] = value
    row["elapsed_seconds"] = time.perf_counter() - started
    return row


def _write_manifest(
    path: Path,
    *,
    status: str,
    completed_rows: int,
    started_at: str,
) -> None:
    model_path = PROJECT_SRC / "reverse_black_box_abm" / "model.py"
    experiments_path = PROJECT_SRC / "reverse_black_box_abm" / "experiments.py"
    protocol_path = EXPERIMENT_DIR / "PROTOCOL.md"
    design_doc_path = ORIGINAL_ROOT.parent / "研究设计.docx"
    payload = {
        **DESIGN,
        "status": status,
        "run_signature": RUN_SIGNATURE,
        "started_at_utc": started_at,
        "updated_at_utc": _utc_now(),
        "completed_rows": int(completed_rows),
        "hashes": {
            "original_model_py": _sha256(model_path),
            "original_experiments_py": _sha256(experiments_path),
            "runner_py": _sha256(Path(__file__).resolve()),
            "protocol_md": _sha256(protocol_path),
            "research_design_docx": _sha256(design_doc_path),
        },
        "runtime": {
            "python": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
    }
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def _existing_keys(raw_path: Path) -> set[tuple[str, float, int]]:
    if not raw_path.exists() or raw_path.stat().st_size == 0:
        return set()
    existing = pd.read_csv(raw_path)
    signatures = set(existing["run_signature"].dropna().astype(str))
    if signatures != {RUN_SIGNATURE}:
        raise RuntimeError(
            "existing raw CSV has a different run signature; refusing to mix runs"
        )
    if existing.duplicated(["condition_id", "alpha", "seed"]).any():
        raise RuntimeError("existing raw CSV contains duplicate primary keys")
    return {
        (str(row.condition_id), round(float(row.alpha), 10), int(row.seed))
        for row in existing.itertuples(index=False)
    }


def _tasks(existing: set[tuple[str, float, int]]) -> list[tuple[str, float, int, int]]:
    pending: list[tuple[str, float, int, int]] = []
    for condition in CONDITIONS:
        condition_id = str(condition["condition_id"])
        for alpha in ALPHAS:
            for replicate, seed in enumerate(SEEDS):
                key = (condition_id, round(float(alpha), 10), int(seed))
                if key not in existing:
                    pending.append((condition_id, float(alpha), replicate, int(seed)))
    return pending


def run(workers: int) -> None:
    raw_dir = EXPERIMENT_DIR / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / "formal_replicates.csv"
    manifest_path = raw_dir / "formal_manifest.json"
    started_at = _utc_now()
    existing = _existing_keys(raw_path)
    pending = _tasks(existing)
    _write_manifest(
        manifest_path,
        status="running" if pending else "complete",
        completed_rows=len(existing),
        started_at=started_at,
    )
    if not pending:
        print("Formal run already complete.")
        return

    print(
        f"Starting {len(pending)} simulations with {workers} workers; "
        f"{len(existing)} rows already present."
    )
    buffer: list[dict[str, Any]] = []
    completed = len(existing)
    header_required = not raw_path.exists() or raw_path.stat().st_size == 0
    with ProcessPoolExecutor(max_workers=workers) as executor:
        for row in executor.map(_run_task, pending, chunksize=4):
            buffer.append(row)
            if len(buffer) >= 50:
                pd.DataFrame(buffer).to_csv(
                    raw_path,
                    mode="a",
                    header=header_required,
                    index=False,
                    encoding="utf-8",
                )
                header_required = False
                completed += len(buffer)
                buffer.clear()
                _write_manifest(
                    manifest_path,
                    status="running",
                    completed_rows=completed,
                    started_at=started_at,
                )
                print(f"Completed {completed}/{DESIGN['expected_rows']}", flush=True)
    if buffer:
        pd.DataFrame(buffer).to_csv(
            raw_path,
            mode="a",
            header=header_required,
            index=False,
            encoding="utf-8",
        )
        completed += len(buffer)

    frame = pd.read_csv(raw_path)
    frame = frame.sort_values(
        ["condition_order", "alpha", "replicate"]
    ).reset_index(drop=True)
    frame.to_csv(raw_path, index=False, encoding="utf-8")
    if len(frame) != DESIGN["expected_rows"]:
        raise RuntimeError(
            f"expected {DESIGN['expected_rows']} rows, found {len(frame)}"
        )
    _write_manifest(
        manifest_path,
        status="complete",
        completed_rows=len(frame),
        started_at=started_at,
    )
    print(f"Formal experiment complete: {raw_path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, min(6, (os.cpu_count() or 2) - 1)),
    )
    arguments = parser.parse_args()
    if arguments.workers <= 0:
        raise SystemExit("--workers must be positive")
    run(arguments.workers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

