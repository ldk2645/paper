"""Run the isolated Version 3 response-cooling experiment.

The pilot is an exploratory signal and pipeline check:
3 alpha values x 2 empirical delay scenarios x 10 common seeds x
2 response heat multipliers = 120 runs.

The formal design is declared but is not run automatically:
21 alpha values x 5 delay scenarios x 50 common seeds x 2 multipliers
= 10,500 runs.
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
V3_ROOT = HERE.parent
MODEL_DIR = V3_ROOT / "01_model"
DATA_DIR = V3_ROOT / "03_data"
if str(MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(MODEL_DIR))

from model_v3 import (  # noqa: E402
    MODEL_VERSION,
    V1_FROZEN_SHA256,
    V2_FROZEN_SHA256,
    Version3Config,
    Version3Simulation,
)


PILOT_DELAY_CONDITIONS: dict[str, int] = {
    "early_p05_11": 11,
    "late_p95_57": 57,
}
FORMAL_DELAY_CONDITIONS: dict[str, int | None] = {
    "v1_reference_3": 3,
    "early_p05_11": 11,
    "case_typical_22": 22,
    "late_p95_57": 57,
    "conditional_empirical_resample": None,
}
HEAT_CONDITIONS: dict[str, float] = {
    "response_heat_100": 1.00,
    "response_heat_070": 0.70,
}
PILOT_ALPHAS = (0.40, 0.60, 0.80)
PILOT_SEEDS = tuple(range(73000, 73010))
FORMAL_ALPHAS = tuple(
    float(value) for value in np.round(np.arange(0.0, 1.0001, 0.05), 2)
)
FORMAL_SEEDS = tuple(range(73000, 73050))

STEP_COLUMNS = [
    "step",
    "alpha",
    "petition_state",
    "petition_visible",
    "petition_heat",
    "petition_exposures",
    "petition_interactions",
    "petition_response_executed",
    "response_heat_before_immediate",
    "response_heat_after_immediate",
    "realized_heat_reduction_fraction",
    "mean_trust",
    "agenda_divergence",
    "official_attention_share",
    "routine_government_posts_published",
    "response_government_posts_published",
    "routine_government_attention_share",
    "routine_government_reach_share",
    "response_government_attention_share",
    "response_government_reach_share",
    "hotspot_demand_misalignment",
    "hotspot_demand_jsd",
    "hotspot_demand_topk_overlap",
    "hotspot_demand_top1_agreement",
    "hotspot_baseline_demand_misalignment",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest().upper()


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
    """Sample once per seed with a stream separate from the ABM."""

    sequence = np.random.SeedSequence([int(seed), 700024, 222, 3])
    rng = np.random.default_rng(sequence)
    sampled = float(empirical_delays[int(rng.integers(0, len(empirical_delays)))])
    return max(1, int(np.rint(sampled)))


def build_tasks(scope: str) -> list[dict[str, Any]]:
    if scope == "pilot":
        delay_conditions: dict[str, int | None] = PILOT_DELAY_CONDITIONS
        alphas = PILOT_ALPHAS
        seeds = PILOT_SEEDS
    elif scope == "formal":
        delay_conditions = FORMAL_DELAY_CONDITIONS
        alphas = FORMAL_ALPHAS
        seeds = FORMAL_SEEDS
    else:
        raise ValueError("scope must be pilot or formal")

    empirical = load_empirical_delays()
    empirical_by_seed = {
        seed: empirical_delay_for_seed(seed, empirical) for seed in seeds
    }
    tasks: list[dict[str, Any]] = []
    for delay_id, fixed_delay in delay_conditions.items():
        for heat_id, multiplier in HEAT_CONDITIONS.items():
            for alpha in alphas:
                for seed in seeds:
                    delay = (
                        fixed_delay
                        if fixed_delay is not None
                        else empirical_by_seed[seed]
                    )
                    tasks.append(
                        {
                            "scope": scope,
                            "delay_condition_id": delay_id,
                            "response_heat_condition_id": heat_id,
                            "response_delay_days": int(delay),
                            "response_heat_multiplier": float(multiplier),
                            "alpha": float(alpha),
                            "seed": int(seed),
                        }
                    )
    return tasks


def _run_id(task: dict[str, Any]) -> str:
    return (
        f"{task['delay_condition_id']}__{task['response_heat_condition_id']}"
        f"__a{float(task['alpha']):.2f}__s{int(task['seed'])}"
    )


def run_one(
    task: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    config = Version3Config.case_700024(
        alpha=float(task["alpha"]),
        seed=int(task["seed"]),
        response_delay=int(task["response_delay_days"]),
        response_heat_multiplier=float(task["response_heat_multiplier"]),
    )
    result = Version3Simulation(config).run()
    run_id = _run_id(task)
    metadata = {
        "run_id": run_id,
        "scope": task["scope"],
        "delay_condition_id": task["delay_condition_id"],
        "response_heat_condition_id": task["response_heat_condition_id"],
        "alpha": float(task["alpha"]),
        "seed": int(task["seed"]),
        "response_delay_days": int(task["response_delay_days"]),
        "response_heat_multiplier": float(task["response_heat_multiplier"]),
    }
    summary = {
        **metadata,
        **result.summary,
        "config_sha256": canonical_hash(config.to_dict()),
    }
    event_rows = [
        {**metadata, **row}
        for row in result.events.to_dict(orient="records")
    ]
    step_rows = [
        {
            **metadata,
            **{column: row[column] for column in STEP_COLUMNS},
        }
        for row in result.metrics[STEP_COLUMNS].to_dict(orient="records")
    ]
    return summary, event_rows, step_rows


def _safe_output_dir(path: Path) -> Path:
    resolved_root = V3_ROOT.resolve()
    resolved = path.resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ValueError("all Version 3 outputs must stay inside its own directory")
    return resolved


def _run_signature(tasks: list[dict[str, Any]]) -> str:
    payload = {
        "model_version": MODEL_VERSION,
        "v1_sha256": V1_FROZEN_SHA256,
        "v2_sha256": V2_FROZEN_SHA256,
        "v3_model_sha256": sha256(MODEL_DIR / "model_v3.py"),
        "runner_sha256": sha256(Path(__file__)),
        "delay_data_sha256": sha256(
            DATA_DIR / "uk_petition_response_delays_222.csv"
        ),
        "tasks": tasks,
    }
    return canonical_hash(payload)


def run_design(
    *,
    scope: str,
    workers: int,
    output_dir: Path,
    overwrite: bool,
) -> tuple[Path, Path, Path, Path]:
    tasks = build_tasks(scope)
    output_dir = _safe_output_dir(output_dir)
    stem = f"v3_{scope}"
    summary_path = output_dir / f"{stem}_run_summaries.csv"
    step_path = output_dir / f"{stem}_step_metrics.csv"
    events_path = output_dir / f"{stem}_event_log.csv"
    manifest_path = output_dir / f"{stem}_manifest.json"
    paths = (summary_path, step_path, events_path, manifest_path)
    existing = [path for path in paths if path.exists()]
    if existing and not overwrite:
        names = ", ".join(path.name for path in existing)
        raise FileExistsError(f"refusing to overwrite V3 outputs: {names}")
    output_dir.mkdir(parents=True, exist_ok=True)

    summaries: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    step_rows: list[dict[str, Any]] = []
    if workers == 1:
        results = map(run_one, tasks)
        for summary, event_part, step_part in results:
            summaries.append(summary)
            events.extend(event_part)
            step_rows.extend(step_part)
    else:
        with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
            for summary, event_part, step_part in executor.map(
                run_one, tasks, chunksize=1
            ):
                summaries.append(summary)
                events.extend(event_part)
                step_rows.extend(step_part)

    key = [
        "delay_condition_id",
        "response_heat_condition_id",
        "alpha",
        "seed",
    ]
    summary_frame = pd.DataFrame.from_records(summaries).sort_values(key)
    event_frame = pd.DataFrame.from_records(events).sort_values(
        key + ["step", "event_type"]
    )
    step_frame = pd.DataFrame.from_records(step_rows).sort_values(key + ["step"])
    expected_runs = 120 if scope == "pilot" else 10_500
    if len(summary_frame) != expected_runs or summary_frame.duplicated(key).any():
        raise RuntimeError("V3 summary panel is incomplete or has duplicate keys")
    if len(step_frame) != expected_runs * 300:
        raise RuntimeError("V3 step panel is incomplete")
    if not summary_frame["routine_government_posts_published"].eq(300).all():
        raise RuntimeError("every V3 run must publish exactly 300 routine items")
    if not summary_frame["response_government_posts_published"].eq(1).all():
        raise RuntimeError("every V3 run must publish exactly one petition response")
    if not summary_frame["responses_executed"].eq(1).all():
        raise RuntimeError("every V3 run must execute exactly one petition response")
    empirical_rows = summary_frame[
        summary_frame["delay_condition_id"].eq("conditional_empirical_resample")
    ]
    if len(empirical_rows) and (
        empirical_rows.groupby("seed")["response_delay_days"].nunique() != 1
    ).any():
        raise RuntimeError(
            "empirical delay must be common across alpha and multiplier per seed"
        )

    model_hash = sha256(MODEL_DIR / "model_v3.py")
    runner_hash = sha256(Path(__file__))
    data_hash = sha256(DATA_DIR / "uk_petition_response_delays_222.csv")
    run_signature = _run_signature(tasks)
    for frame in (summary_frame, step_frame, event_frame):
        frame["v1_parent_sha256"] = V1_FROZEN_SHA256
        frame["v2_parent_sha256"] = V2_FROZEN_SHA256
        frame["v3_model_sha256"] = model_hash
        frame["runner_sha256"] = runner_hash
        frame["run_signature"] = run_signature
    summary_frame["delay_data_sha256"] = data_hash

    summary_frame.to_csv(summary_path, index=False, encoding="utf-8-sig")
    step_frame.to_csv(step_path, index=False, encoding="utf-8-sig")
    event_frame.to_csv(events_path, index=False, encoding="utf-8-sig")
    manifest = {
        "status": "complete",
        "scope": scope,
        "evidence_status": (
            "exploratory_pilot_not_formal_evidence"
            if scope == "pilot"
            else "formal_design_complete"
        ),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "model_version": MODEL_VERSION,
        "v1_parent_sha256": V1_FROZEN_SHA256,
        "v2_parent_sha256": V2_FROZEN_SHA256,
        "v3_model_sha256": model_hash,
        "runner_sha256": runner_hash,
        "delay_data_sha256": data_hash,
        "run_signature": run_signature,
        "completed_runs": len(summary_frame),
        "step_rows": len(step_frame),
        "event_rows": len(event_frame),
        "primary_estimand": (
            "paired difference-in-differences in log1p 14-day post-response "
            "petition-heat AUC"
        ),
        "alpha_values": sorted(summary_frame["alpha"].unique().tolist()),
        "seed_values": sorted(int(value) for value in summary_frame["seed"].unique()),
        "delay_condition_ids": sorted(
            summary_frame["delay_condition_id"].unique().tolist()
        ),
        "response_heat_multipliers": sorted(
            summary_frame["response_heat_multiplier"].unique().tolist()
        ),
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
    return summary_path, step_path, events_path, manifest_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=("pilot", "formal"), default="pilot")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.workers < 1:
        raise ValueError("workers must be at least one")
    output_dir = args.output_dir or V3_ROOT / "05_outputs" / args.scope
    for path in run_design(
        scope=args.scope,
        workers=args.workers,
        output_dir=output_dir,
        overwrite=args.overwrite,
    ):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
