"""Run the formal non-spatial sensitivity experiment without editing model.py.

The frozen model is imported from ``../01_model_core/model.py``. Parameter and
built-in response-strategy scenarios only replace SimulationConfig values.
Three execution-order checks are isolated subclasses in this runner; they do
not modify the frozen model. Every scenario uses 21 alpha levels and the same
50 seeds as the formal ablation experiment.
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
from dataclasses import asdict
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

import pandas as pd


HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
MODEL_PATH = PACKAGE / "01_model_core" / "model.py"
RAW_DIR = PACKAGE / "03_data" / "sensitivity" / "raw"
RAW_PATH = RAW_DIR / "sensitivity_replicates.csv"
MANIFEST_PATH = RAW_DIR / "sensitivity_manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_hash(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_model():
    spec = importlib.util.spec_from_file_location("frozen_nonspatial_model", MODEL_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to import frozen model: {MODEL_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


model = load_model()
SimulationConfig = model.SimulationConfig
ReverseBlackBoxSimulation = model.ReverseBlackBoxSimulation


class NewInformationAfterRecommendationSimulation(ReverseBlackBoxSimulation):
    """Generate each step's new spontaneous items after current public action."""

    def __init__(self, config):
        self._defer_spontaneous = False
        self._deferred_spontaneous: tuple[int, int] | None = None
        super().__init__(config)
        self._defer_spontaneous = True

    def _add_spontaneous_information(self, *, step: int, count: int) -> None:
        if not self._defer_spontaneous:
            return super()._add_spontaneous_information(step=step, count=count)
        if self._deferred_spontaneous is not None:
            raise RuntimeError("deferred spontaneous-information buffer is occupied")
        self._deferred_spontaneous = (step, count)

    def _public_action(self, recommendations, topics, emotions, sources):
        result = super()._public_action(recommendations, topics, emotions, sources)
        if self._deferred_spontaneous is not None:
            step, count = self._deferred_spontaneous
            self._deferred_spontaneous = None
            ReverseBlackBoxSimulation._add_spontaneous_information(
                self, step=step, count=count
            )
        return result


class GovernmentActionAtStepEndSimulation(ReverseBlackBoxSimulation):
    """Move publication/response execution to the end of each model step."""

    def __init__(self, config):
        self._government_carry = (0.0, 0)
        self._government_end_step: int | None = None
        super().__init__(config)

    def _government_action(self, step: int):
        carry = self._government_carry
        self._government_carry = (0.0, 0)
        self._government_end_step = step
        return carry

    def _decay_and_prune(self, step: int) -> None:
        if self._government_end_step != step:
            raise RuntimeError("government end-step hook is out of sync")
        self._government_carry = ReverseBlackBoxSimulation._government_action(
            self, step
        )
        self._government_end_step = None
        ReverseBlackBoxSimulation._decay_and_prune(self, step)


class DecayBeforeRecommendationSimulation(ReverseBlackBoxSimulation):
    """Apply heat decay/pruning after government action and before recommendation."""

    def __init__(self, config):
        self._skip_end_decay = False
        super().__init__(config)

    def _government_action(self, step: int):
        result = ReverseBlackBoxSimulation._government_action(self, step)
        ReverseBlackBoxSimulation._decay_and_prune(self, step)
        self._skip_end_decay = True
        return result

    def _decay_and_prune(self, step: int) -> None:
        if not self._skip_end_decay:
            raise RuntimeError("pre-recommendation decay hook is out of sync")
        self._skip_end_decay = False


ALPHAS = tuple(round(index * 0.05, 2) for index in range(21))
SEEDS = tuple(range(73000, 73050))

SCENARIOS: tuple[dict[str, Any], ...] = (
    {"scenario_id": "heat_decay_090", "scenario_kind": "parameter", "parameter": "heat_decay", "value": 0.90, "overrides": {"heat_decay": 0.90}},
    {"scenario_id": "heat_decay_085", "scenario_kind": "parameter", "parameter": "heat_decay", "value": 0.85, "overrides": {"heat_decay": 0.85}},
    {"scenario_id": "response_delay_5", "scenario_kind": "parameter", "parameter": "response_delay", "value": 5, "overrides": {"response_delay": 5}},
    {"scenario_id": "response_delay_8", "scenario_kind": "parameter", "parameter": "response_delay", "value": 8, "overrides": {"response_delay": 8}},
    {"scenario_id": "drift_rate_005", "scenario_kind": "parameter", "parameter": "preference_drift_rate", "value": 0.05, "overrides": {"preference_drift_rate": 0.05}},
    {"scenario_id": "drift_rate_001", "scenario_kind": "parameter", "parameter": "preference_drift_rate", "value": 0.01, "overrides": {"preference_drift_rate": 0.01}},
    {"scenario_id": "trust_update_012", "scenario_kind": "parameter", "parameter": "trust_update_rate", "value": 0.12, "overrides": {"trust_update_rate": 0.12}},
    {"scenario_id": "trust_update_003", "scenario_kind": "parameter", "parameter": "trust_update_rate", "value": 0.03, "overrides": {"trust_update_rate": 0.03}},
    {"scenario_id": "trust_feedback_050", "scenario_kind": "parameter", "parameter": "trust_feedback_strength", "value": 0.50, "overrides": {"trust_feedback_strength": 0.50}},
    {"scenario_id": "trust_feedback_010", "scenario_kind": "parameter", "parameter": "trust_feedback_strength", "value": 0.10, "overrides": {"trust_feedback_strength": 0.10}},
    {"scenario_id": "response_threshold_030", "scenario_kind": "parameter", "parameter": "response_threshold", "value": 0.30, "overrides": {"response_threshold": 0.30}},
    {"scenario_id": "response_threshold_010", "scenario_kind": "parameter", "parameter": "response_threshold", "value": 0.10, "overrides": {"response_threshold": 0.10}},
    {"scenario_id": "response_retention_090", "scenario_kind": "parameter", "parameter": "response_strength", "value": 0.90, "overrides": {"response_strength": 0.90}},
    {"scenario_id": "response_retention_050", "scenario_kind": "parameter", "parameter": "response_strength", "value": 0.50, "overrides": {"response_strength": 0.50}},
    {"scenario_id": "strategy_selective", "scenario_kind": "response_strategy", "parameter": "response_strategy", "value": "selective", "overrides": {"response_strategy": "selective"}},
    {"scenario_id": "strategy_wait", "scenario_kind": "response_strategy", "parameter": "response_strategy", "value": "wait", "overrides": {"response_strategy": "wait"}},
    {"scenario_id": "order_new_information_after_recommendation", "scenario_kind": "execution_order", "parameter": "execution_order", "value": "new_information_after_recommendation", "overrides": {}, "simulation_class": "new_information_after_recommendation"},
    {"scenario_id": "order_government_action_at_end", "scenario_kind": "execution_order", "parameter": "execution_order", "value": "government_action_at_end", "overrides": {}, "simulation_class": "government_action_at_end"},
    {"scenario_id": "order_decay_before_recommendation", "scenario_kind": "execution_order", "parameter": "execution_order", "value": "decay_before_recommendation", "overrides": {}, "simulation_class": "decay_before_recommendation"},
)

SCENARIO_MAP = {str(item["scenario_id"]): item for item in SCENARIOS}
SIMULATION_CLASSES = {
    "default": ReverseBlackBoxSimulation,
    "new_information_after_recommendation": NewInformationAfterRecommendationSimulation,
    "government_action_at_end": GovernmentActionAtStepEndSimulation,
    "decay_before_recommendation": DecayBeforeRecommendationSimulation,
}

DESIGN = {
    "analysis_status": "formal_nonspatial_sensitivity_v1",
    "model_family": "frozen_nonspatial_global_information_pool",
    "model_sha256": sha256(MODEL_PATH),
    "alphas": list(ALPHAS),
    "seeds": list(SEEDS),
    "replicates_per_cell": len(SEEDS),
    "scenarios": list(SCENARIOS),
    "steady_state_window": 100,
    "expected_rows": len(SCENARIOS) * len(ALPHAS) * len(SEEDS),
}
RUN_SIGNATURE = json_hash(DESIGN)


def configuration_for(scenario_id: str, alpha: float, seed: int):
    scenario = SCENARIO_MAP[scenario_id]
    return SimulationConfig(alpha=float(alpha), seed=int(seed), **scenario["overrides"])


def run_task(task: tuple[str, float, int, int]) -> dict[str, Any]:
    scenario_id, alpha, replicate, seed = task
    scenario = SCENARIO_MAP[scenario_id]
    config = configuration_for(scenario_id, alpha, seed)
    class_name = str(scenario.get("simulation_class", "default"))
    simulation_class = SIMULATION_CLASSES[class_name]
    started = time.perf_counter()
    result = simulation_class(config).run()
    row: dict[str, Any] = {
        "analysis_status": DESIGN["analysis_status"],
        "run_signature": RUN_SIGNATURE,
        "scenario_id": scenario_id,
        "scenario_kind": scenario["scenario_kind"],
        "parameter": scenario["parameter"],
        "value": scenario["value"],
        "simulation_class": class_name,
        "replicate": int(replicate),
        "seed": int(seed),
        "alpha": float(alpha),
        "configuration_json": json.dumps(asdict(config), ensure_ascii=False, sort_keys=True),
        "configuration_sha256": json_hash(asdict(config)),
    }
    for key, value in result.summary.items():
        if key not in {"alpha", "seed"}:
            row[key] = value
    row["elapsed_seconds"] = time.perf_counter() - started
    return row


def existing_keys() -> set[tuple[str, float, int]]:
    if not RAW_PATH.exists() or RAW_PATH.stat().st_size == 0:
        return set()
    frame = pd.read_csv(RAW_PATH)
    if set(frame["run_signature"].astype(str)) != {RUN_SIGNATURE}:
        raise RuntimeError("Existing sensitivity CSV has a different run signature")
    if frame.duplicated(["scenario_id", "alpha", "seed"]).any():
        raise RuntimeError("Existing sensitivity CSV has duplicate primary keys")
    return {
        (str(row.scenario_id), round(float(row.alpha), 10), int(row.seed))
        for row in frame.itertuples(index=False)
    }


def pending_tasks(existing: set[tuple[str, float, int]]):
    tasks: list[tuple[str, float, int, int]] = []
    for scenario in SCENARIOS:
        scenario_id = str(scenario["scenario_id"])
        for alpha in ALPHAS:
            for replicate, seed in enumerate(SEEDS):
                key = (scenario_id, round(float(alpha), 10), int(seed))
                if key not in existing:
                    tasks.append((scenario_id, float(alpha), replicate, int(seed)))
    return tasks


def write_manifest(status: str, completed_rows: int, started_at: str) -> None:
    payload = {
        **DESIGN,
        "run_signature": RUN_SIGNATURE,
        "status": status,
        "completed_rows": int(completed_rows),
        "started_at_utc": started_at,
        "updated_at_utc": utc_now(),
        "runner_sha256": sha256(Path(__file__).resolve()),
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "pandas": pd.__version__,
        },
    }
    temporary = MANIFEST_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(MANIFEST_PATH)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=max(1, min(7, os.cpu_count() or 2)))
    args = parser.parse_args()
    if args.workers <= 0:
        raise SystemExit("--workers must be positive")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    started_at = utc_now()
    existing = existing_keys()
    tasks = pending_tasks(existing)
    write_manifest("running" if tasks else "complete", len(existing), started_at)
    if not tasks:
        print(f"Sensitivity experiment already complete: {RAW_PATH}")
        return 0

    print(
        f"Starting {len(tasks):,} simulations with {args.workers} workers; "
        f"{len(existing):,} rows already present.",
        flush=True,
    )
    buffer: list[dict[str, Any]] = []
    completed = len(existing)
    header = not RAW_PATH.exists() or RAW_PATH.stat().st_size == 0
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        for row in executor.map(run_task, tasks, chunksize=4):
            buffer.append(row)
            if len(buffer) >= 50:
                pd.DataFrame(buffer).to_csv(
                    RAW_PATH, mode="a", header=header, index=False, encoding="utf-8"
                )
                header = False
                completed += len(buffer)
                buffer.clear()
                write_manifest("running", completed, started_at)
                print(f"Completed {completed:,}/{DESIGN['expected_rows']:,}", flush=True)
    if buffer:
        pd.DataFrame(buffer).to_csv(
            RAW_PATH, mode="a", header=header, index=False, encoding="utf-8"
        )
        completed += len(buffer)

    frame = pd.read_csv(RAW_PATH)
    order = {item["scenario_id"]: index for index, item in enumerate(SCENARIOS)}
    frame["scenario_order"] = frame["scenario_id"].map(order)
    frame = frame.sort_values(["scenario_order", "alpha", "seed"]).drop(columns="scenario_order")
    frame.to_csv(RAW_PATH, index=False, encoding="utf-8")
    if len(frame) != DESIGN["expected_rows"]:
        raise RuntimeError(
            f"Expected {DESIGN['expected_rows']:,} rows, found {len(frame):,}"
        )
    write_manifest("complete", len(frame), started_at)
    print(f"Sensitivity experiment complete: {RAW_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
