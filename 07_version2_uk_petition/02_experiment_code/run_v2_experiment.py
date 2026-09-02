"""Run UK-petition Version 2 delay scenarios with reproducible seeds.

The formal design contains five delay conditions x 21 alpha values x 50 common
seeds = 5,250 runs.  The default smoke scope is deliberately small and its
outputs must not be reported as formal evidence.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import scipy


HERE = Path(__file__).resolve().parent
V2_ROOT = HERE.parent
MODEL_DIR = V2_ROOT / "01_model"
DATA_DIR = V2_ROOT / "03_data"
if str(MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(MODEL_DIR))

from model_v2 import (  # noqa: E402
    MODEL_VERSION,
    UKPetitionConfig,
    UKPetitionSimulation,
    V1_FROZEN_SHA256,
)


DELAY_CONDITIONS: dict[str, int | None] = {
    "v1_reference_3": 3,
    "conditional_p05_11": 11,
    "case_typical_22": 22,
    "conditional_p95_57": 57,
    "conditional_empirical_resample": None,
}
FORMAL_ALPHAS = tuple(float(value) for value in np.round(np.arange(0, 1.0001, 0.05), 2))
FORMAL_SEEDS = tuple(range(73000, 73050))
SMOKE_ALPHAS = (0.40, 0.60, 0.80)
SMOKE_SEEDS = (73000,)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def load_empirical_delays(path: Path | None = None) -> np.ndarray:
    source = path or DATA_DIR / "uk_petition_response_delays_222.csv"
    frame = pd.read_csv(source)
    required = {"petition_id", "response_delay_days"}
    if set(frame.columns) != required:
        raise ValueError(f"delay table columns must be exactly {sorted(required)}")
    if len(frame) != 222 or frame["petition_id"].duplicated().any():
        raise ValueError("delay table must contain 222 unique petitions")
    delays = frame["response_delay_days"].to_numpy(dtype=float)
    if not np.isfinite(delays).all() or np.any(delays <= 0):
        raise ValueError("all empirical delays must be finite and positive")
    return delays


def empirical_delay_for_seed(seed: int, empirical_delays: np.ndarray) -> int:
    """Select one delay per seed using a random stream separate from the ABM."""

    sequence = np.random.SeedSequence([int(seed), 700024, 222, 2])
    rng = np.random.default_rng(sequence)
    sampled = float(empirical_delays[int(rng.integers(0, len(empirical_delays)))])
    return max(1, int(np.rint(sampled)))


def build_tasks(scope: str) -> list[dict[str, Any]]:
    empirical = load_empirical_delays()
    if scope == "formal":
        alphas = FORMAL_ALPHAS
        seeds = FORMAL_SEEDS
    elif scope == "smoke":
        alphas = SMOKE_ALPHAS
        seeds = SMOKE_SEEDS
    else:
        raise ValueError("scope must be smoke or formal")

    empirical_by_seed = {
        seed: empirical_delay_for_seed(seed, empirical) for seed in seeds
    }
    tasks: list[dict[str, Any]] = []
    for condition_id, fixed_delay in DELAY_CONDITIONS.items():
        for alpha in alphas:
            for seed in seeds:
                tasks.append(
                    {
                        "scope": scope,
                        "condition_id": condition_id,
                        "alpha": alpha,
                        "seed": seed,
                        "response_delay_days": (
                            fixed_delay
                            if fixed_delay is not None
                            else empirical_by_seed[seed]
                        ),
                    }
                )
    return tasks


def run_one(task: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    config = UKPetitionConfig.case_700024(
        alpha=float(task["alpha"]),
        seed=int(task["seed"]),
        response_delay=int(task["response_delay_days"]),
    )
    result = UKPetitionSimulation(config).run()
    run_id = (
        f"{task['condition_id']}__a{float(task['alpha']):.2f}"
        f"__s{int(task['seed'])}"
    )
    summary = {
        "run_id": run_id,
        "scope": task["scope"],
        "condition_id": task["condition_id"],
        **result.summary,
    }
    event_rows = []
    for row in result.events.to_dict(orient="records"):
        event_rows.append(
            {
                "run_id": run_id,
                "scope": task["scope"],
                "condition_id": task["condition_id"],
                "alpha": float(task["alpha"]),
                "seed": int(task["seed"]),
                "response_delay_days": int(task["response_delay_days"]),
                **row,
            }
        )
    return summary, event_rows


def _safe_output_dir(path: Path) -> Path:
    resolved_root = V2_ROOT.resolve()
    resolved = path.resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ValueError("all Version 2 outputs must stay inside its own directory")
    return resolved


def _run_signature(tasks: list[dict[str, Any]]) -> str:
    payload = {
        "model_version": MODEL_VERSION,
        "v1_sha256": V1_FROZEN_SHA256,
        "v2_model_sha256": sha256(MODEL_DIR / "model_v2.py"),
        "runner_sha256": sha256(Path(__file__)),
        "delay_data_sha256": sha256(DATA_DIR / "uk_petition_response_delays_222.csv"),
        "tasks": tasks,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest().upper()


def run_design(
    *,
    scope: str,
    workers: int,
    output_dir: Path,
    overwrite: bool,
) -> tuple[Path, Path, Path]:
    tasks = build_tasks(scope)
    output_dir = _safe_output_dir(output_dir)
    summary_path = output_dir / "v2_run_summaries.csv"
    events_path = output_dir / "v2_event_log.csv"
    manifest_path = output_dir / "v2_run_manifest.json"
    existing = [path for path in (summary_path, events_path, manifest_path) if path.exists()]
    if existing and not overwrite:
        names = ", ".join(path.name for path in existing)
        raise FileExistsError(f"refusing to overwrite existing V2 outputs: {names}")
    output_dir.mkdir(parents=True, exist_ok=True)

    summaries: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    if workers == 1:
        results = map(run_one, tasks)
        for summary, event_rows in results:
            summaries.append(summary)
            events.extend(event_rows)
    else:
        with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
            for summary, event_rows in executor.map(run_one, tasks, chunksize=1):
                summaries.append(summary)
                events.extend(event_rows)

    summary_frame = pd.DataFrame.from_records(summaries).sort_values(
        ["condition_id", "alpha", "seed"]
    )
    event_frame = pd.DataFrame.from_records(events).sort_values(
        ["condition_id", "alpha", "seed", "step", "event_type"]
    )
    expected_rows = len(tasks)
    key = ["condition_id", "alpha", "seed"]
    if len(summary_frame) != expected_rows or summary_frame.duplicated(key).any():
        raise RuntimeError("run summary panel is incomplete or has duplicate keys")
    if scope == "formal" and expected_rows != 5250:
        raise RuntimeError("formal Version 2 design must contain exactly 5,250 runs")
    empirical = summary_frame[
        summary_frame["condition_id"].eq("conditional_empirical_resample")
    ]
    if (empirical.groupby("seed")["response_delay_days"].nunique() != 1).any():
        raise RuntimeError("empirical delay must be constant over alpha for each seed")

    model_hash = sha256(MODEL_DIR / "model_v2.py")
    runner_hash = sha256(Path(__file__))
    delay_data_hash = sha256(DATA_DIR / "uk_petition_response_delays_222.csv")
    run_signature = _run_signature(tasks)
    summary_frame["v1_parent_sha256"] = V1_FROZEN_SHA256
    summary_frame["v2_model_sha256"] = model_hash
    summary_frame["runner_sha256"] = runner_hash
    summary_frame["delay_data_sha256"] = delay_data_hash
    summary_frame["run_signature"] = run_signature

    summary_frame.to_csv(summary_path, index=False, encoding="utf-8-sig")
    event_frame.to_csv(events_path, index=False, encoding="utf-8-sig")
    manifest = {
        "status": "complete",
        "scope": scope,
        "evidence_status": (
            "smoke_only_not_formal_evidence" if scope == "smoke" else "formal_design"
        ),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "model_version": MODEL_VERSION,
        "v1_parent_sha256": V1_FROZEN_SHA256,
        "v2_model_sha256": model_hash,
        "runner_sha256": runner_hash,
        "delay_data_sha256": delay_data_hash,
        "run_signature": run_signature,
        "completed_rows": len(summary_frame),
        "event_rows": len(event_frame),
        "condition_ids": list(DELAY_CONDITIONS),
        "alpha_values": sorted(summary_frame["alpha"].unique().tolist()),
        "seed_values": sorted(int(value) for value in summary_frame["seed"].unique()),
        "workers": workers,
        "python": sys.version,
        "platform": platform.platform(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scipy": scipy.__version__,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary_path, events_path, manifest_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=("smoke", "formal"), default="smoke")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace outputs inside the selected Version 2 output directory",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.workers < 1:
        raise ValueError("workers must be at least 1")
    output_dir = args.output_dir or V2_ROOT / "05_outputs" / args.scope
    paths = run_design(
        scope=args.scope,
        workers=args.workers,
        output_dir=output_dir,
        overwrite=args.overwrite,
    )
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
