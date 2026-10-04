"""Prespecified small structural diagnostics, not a confirmatory main experiment."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys


CASES = {
    "baseline": {},
    "no_emotion_advantage": {"emotion_advantage": 0.0},
    "reversed_emotion_advantage": {"emotion_advantage": -0.25},
    "softmax_ranking": {"ranking": "softmax"},
    "matched_panel": {"platform_panel_size": 12},
    "longer_cold_start": {"cold_start_rounds": 5},
    "biased_noisy_survey": {"survey_selection_bias": 5.0, "survey_noise_sd": 0.1},
    "preference_drift": {"drift_rate": 0.03},
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("Use a new output directory")
    output.mkdir(parents=True, exist_ok=True)
    base = json.loads((project / "configs" / "pilot.json").read_text())
    combined = []
    for name, changes in CASES.items():
        spec = {**base, "model": {**base["model"], **changes}}
        config = output / f"{name}.json"
        config.write_text(json.dumps(spec, indent=2), encoding="utf-8")
        command = [sys.executable, "-m", "abm_jasss.cli", "--config", str(config),
                   "--output", str(output / name), "--workers", str(args.workers)]
        run = subprocess.run(command, cwd=project, capture_output=True, text=True)
        (output / f"{name}.log").write_text(run.stdout + run.stderr, encoding="utf-8")
        if run.returncode:
            raise SystemExit(f"{name} failed; inspect its log")
        with (output / name / "aggregate.csv").open(encoding="utf-8", newline="") as f:
            combined.extend({"scenario": name, **row} for row in csv.DictReader(f))
        print(f"Completed {name}", flush=True)
    with (output / "all_aggregates.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(combined[0]))
        writer.writeheader()
        writer.writerows(combined)


if __name__ == "__main__":
    main()
