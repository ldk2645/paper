"""Run the fifth formal ablation: remove trust-to-interaction feedback.

The trust state is still updated and observed.  Only its feedback into public
interaction probabilities is removed by setting trust_feedback_strength=0.
This isolates the feedback mechanism without turning the outcome into a
constant or changing the trust equation itself.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(name, "1")

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
OUT = HERE.parent
WORKSPACE = OUT.parent
FORMAL = WORKSPACE / "原始版本" / "formal_ablation_n50_nonspatial"
RUNNER_PATH = FORMAL / "run_formal_ablation.py"
RAW_PATH = OUT / "raw" / "no_trust_replicates.csv"
MANIFEST_PATH = OUT / "raw" / "no_trust_manifest.json"
ALPHAS = tuple(round(i * 0.05, 2) for i in range(21))
SEEDS = tuple(range(73000, 73050))
STATUS = "formal_nonspatial_no_trust_v1"


def load_runner():
    spec = importlib.util.spec_from_file_location("formal_runner_5", RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load formal runner")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


formal = load_runner()


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def config_for(alpha: float, seed: int):
    baseline = formal._configuration_for("full", alpha, seed)
    return replace(baseline, trust_feedback_strength=0.0)


def run_one(task: tuple[float, int, int]) -> dict:
    alpha, replicate, seed = task
    config = config_for(alpha, seed)
    started = time.perf_counter()
    result = formal.UnifiedNonSpatialSimulation(config).run()
    row = {
        "analysis_status": STATUS,
        "condition_id": "no_trust",
        "condition_order": 4,
        "condition_label": "No trust feedback",
        "removed_mechanism": "trust_feedback",
        "emotion_advantage_enabled": True,
        "preference_drift_rate": config.preference_drift_rate,
        "response_strength": config.response_strength,
        "trust_feedback_strength": config.trust_feedback_strength,
        "replicate": replicate,
        "seed": seed,
        "alpha": alpha,
        "configuration": json.dumps(asdict(config), ensure_ascii=False, sort_keys=True),
    }
    row.update({key: value for key, value in result.summary.items() if key not in {"alpha", "seed"}})
    row["elapsed_seconds"] = time.perf_counter() - started
    return row


def existing_keys() -> set[tuple[float, int]]:
    if not RAW_PATH.exists() or RAW_PATH.stat().st_size == 0:
        return set()
    frame = pd.read_csv(RAW_PATH)
    if frame.duplicated(["alpha", "seed"]).any():
        raise RuntimeError("Duplicate alpha-seed keys in existing no-trust file")
    return {(round(float(row.alpha), 10), int(row.seed)) for row in frame.itertuples(index=False)}


def write_manifest(status: str, completed: int, started_at: str) -> None:
    baseline = asdict(config_for(0.5, SEEDS[0]))
    payload = {
        "analysis_status": STATUS,
        "status": status,
        "condition": "no_trust",
        "removed_mechanism": "trust-to-interaction feedback",
        "operational_definition": "trust_feedback_strength = 0; trust state update remains active",
        "model_family": "original_nonspatial_global_information_pool",
        "alphas": list(ALPHAS),
        "seeds": list(SEEDS),
        "replicates_per_alpha": len(SEEDS),
        "expected_rows": len(ALPHAS) * len(SEEDS),
        "completed_rows": completed,
        "started_at_utc": started_at,
        "updated_at_utc": utc_now(),
        "baseline_no_trust_config": baseline,
        "hashes": {
            "formal_runner": digest(RUNNER_PATH),
            "original_model": digest(WORKSPACE / "原始版本" / "src" / "src" / "reverse_black_box_abm" / "model.py"),
            "this_runner": digest(Path(__file__)),
        },
        "runtime": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "platform": platform.platform(),
        },
    }
    MANIFEST_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=max(1, min(8, (os.cpu_count() or 2) - 1)))
    args = parser.parse_args()
    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    started_at = utc_now()
    done = existing_keys()
    tasks = [
        (alpha, replicate, seed)
        for alpha in ALPHAS
        for replicate, seed in enumerate(SEEDS)
        if (round(alpha, 10), seed) not in done
    ]
    write_manifest("running", len(done), started_at)
    print(json.dumps({"expected": 1050, "already_complete": len(done), "pending": len(tasks), "workers": args.workers}))

    rows: list[dict] = []
    if tasks:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            for index, row in enumerate(pool.map(run_one, tasks, chunksize=4), start=1):
                rows.append(row)
                if index % 100 == 0:
                    print(json.dumps({"new_completed": index, "pending": len(tasks) - index}), flush=True)
        new = pd.DataFrame(rows)
        if RAW_PATH.exists() and RAW_PATH.stat().st_size:
            old = pd.read_csv(RAW_PATH)
            new = pd.concat([old, new], ignore_index=True)
        new = new.sort_values(["alpha", "seed"]).reset_index(drop=True)
        new.to_csv(RAW_PATH, index=False, encoding="utf-8")

    final = pd.read_csv(RAW_PATH)
    if len(final) != 1050 or set(final.groupby("alpha").size()) != {50}:
        raise RuntimeError("No-trust experiment is incomplete")
    write_manifest("complete", len(final), started_at)
    print(json.dumps({"status": "complete", "rows": len(final)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

