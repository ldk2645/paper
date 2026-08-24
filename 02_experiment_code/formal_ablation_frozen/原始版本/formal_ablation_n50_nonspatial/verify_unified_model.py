"""Result-blind verification of the unified non-spatial ablation switches."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
ORIGINAL_ROOT = HERE.parent
PROJECT_SRC = ORIGINAL_ROOT / "src" / "src"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PROJECT_SRC))

from reverse_black_box_abm.model import (  # noqa: E402
    ReverseBlackBoxSimulation,
    SimulationConfig,
)
from run_formal_ablation import (  # noqa: E402
    UnifiedNonSpatialConfig,
    UnifiedNonSpatialSimulation,
    _configuration_for,
)


def main() -> int:
    checked = 0
    for alpha in (0.0, 0.6, 1.0):
        for seed in (73000, 73001):
            base = ReverseBlackBoxSimulation(
                SimulationConfig(alpha=alpha, seed=seed)
            ).run()
            unified = UnifiedNonSpatialSimulation(
                UnifiedNonSpatialConfig(alpha=alpha, seed=seed)
            ).run()
            for key, value in base.summary.items():
                if isinstance(value, (int, float)):
                    if not np.isclose(value, unified.summary[key], rtol=0, atol=0):
                        raise AssertionError(
                            f"full-model mismatch at {alpha=}, {seed=}, {key=}"
                        )
                elif value != unified.summary[key]:
                    raise AssertionError(
                        f"full-model mismatch at {alpha=}, {seed=}, {key=}"
                    )
            checked += 1

    drift_config = _configuration_for("no_drift", 0.6, 73000)
    drift_simulation = UnifiedNonSpatialSimulation(drift_config)
    initial_preferences = drift_simulation.preferences.copy()
    drift_simulation.run()
    if not np.array_equal(initial_preferences, drift_simulation.preferences):
        raise AssertionError("no_drift changed preferences")

    response_config = _configuration_for("no_response", 0.6, 73000)
    response_result = UnifiedNonSpatialSimulation(response_config).run()
    if not np.allclose(response_result.metrics["response_effect"], 0.0):
        raise AssertionError("no_response produced a non-zero response effect")
    if response_result.summary["responses_executed"] <= 0:
        raise AssertionError("no_response did not preserve no-effect response events")

    emotion_config = _configuration_for("no_emotion", 0.6, 73000)
    emotion_simulation = UnifiedNonSpatialSimulation(emotion_config)
    draws = np.asarray(
        [emotion_simulation._sample_spontaneous_emotion(3) for _ in range(20000)]
    )
    if not 0.38 < float(draws.mean()) < 0.42:
        raise AssertionError("no_emotion does not follow Beta(2,3) expectation")

    output = HERE / "processed" / "unified_model_verification.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "status": "PASS",
                "exact_full_model_comparisons": checked,
                "full_model_exact_match": True,
                "no_drift_preferences_unchanged": True,
                "no_response_effect_always_zero": True,
                "no_response_events_preserved": True,
                "no_emotion_beta_2_3_sample_mean": float(draws.mean()),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        "Unified-model verification PASS: "
        f"{checked} exact full-model comparisons plus mechanism checks."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
