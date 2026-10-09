"""Check provenance, event accounting and stored results of the restored pilot."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(output):
    suite = read_json(output / "suite_manifest.json")
    worlds = trajectories = event_files = records = 0
    current_matches = True
    for case in suite["cases"]:
        folder = output / case
        manifest = read_json(folder / "manifest.json")
        require(manifest["status"] == "complete" and manifest["failed_world_runs"] == 0, case)
        require(manifest["model_version"] == "0.4.0", f"Unexpected version: {case}")
        for name, expected in manifest["source_sha256"].items():
            actual = hashlib.sha256((folder / "source_snapshot/abm_jasss" / name).read_bytes()).hexdigest()
            require(actual == expected, f"Snapshot hash mismatch: {case}/{name}")
            current_matches &= hashlib.sha256((ROOT / "abm_jasss" / name).read_bytes()).hexdigest() == expected
        jobs = read_json(folder / "resolved_design.json")
        identifiers = {job["run_id"] for job in jobs}
        require(len(jobs) == len(identifiers) == manifest["successful_world_runs"], f"Design count: {case}")
        require(identifiers == {p.stem for p in (folder / "trajectories").glob("*.csv")}, f"Trajectories: {case}")
        require(identifiers == {p.stem for p in (folder / "events").glob("*.json")}, f"Event files: {case}")
        require(len(read_csv(folder / "runs.csv")) == len(jobs), f"Summary count: {case}")
        for job in jobs:
            ident, cfg = job["run_id"], job["model"]
            series = read_csv(folder / "trajectories" / f"{ident}.csv")
            record = read_json(folder / f"{ident}.json")
            event_data = read_json(folder / "events" / f"{ident}.json")
            require(record["seed"] == job["seed"] and record["config"] == cfg, f"Resolved config: {case}/{ident}")
            require([int(r["step"]) for r in series] == list(range(cfg["steps"])), f"Step coverage: {ident}")
            for row in series:
                require(all(math.isfinite(float(value)) for value in row.values()), f"Nonfinite trajectory: {ident}")
                for prefix in ("truth", "attention"):
                    values = [float(row[f"{prefix}_{k}"]) for k in range(cfg["n_topics"])]
                    require(min(values) >= 0 and abs(sum(values) - 1) < 1e-10, f"Distribution: {ident}")
            scheduled = [e for e in event_data["events"] if e["kind"] == "response_scheduled"]
            executed = [e for e in event_data["events"] if e["kind"] == "response_executed"]
            pending = event_data["pending_responses"]
            require(len(scheduled) == len(executed) + len(pending), f"Response accounting: {ident}")
            keys = {(e["topic"], e["trigger_step"], e["due_step"]) for e in scheduled}
            for e in executed + pending:
                require((e["topic"], e["trigger_step"], e["due_step"]) in keys, f"Orphan response: {ident}")
                require(e["due_step"] - e["trigger_step"] == cfg["government_delay"], f"Delay: {ident}")
            for e in executed:
                require(e["step"] == e["due_step"], f"Execution time: {ident}")
                require(abs(e["heat_after_immediate"] - cfg["response_heat_retention"] * e["heat_before"]) < 1e-8,
                        f"Heat action: {ident}")
            require(all(e["due_step"] >= cfg["steps"] for e in pending), f"Unexecuted due response: {ident}")
            summary = record["summary"][0]
            require(summary["responses_scheduled"] == len(scheduled) and summary["responses_executed"] == len(executed),
                    f"Summary response count: {ident}")
            for episode in event_data["storm_episodes"]:
                require(episode["right_censored"] == (episode["end_step"] == cfg["steps"] - 1), f"Censoring: {ident}")
                require(episode["duration"] == episode["end_step"] - episode["start_step"] + 1, f"Episode duration: {ident}")
            worlds += 1
            trajectories += 1
            event_files += 1
            records += len(series)
    require(suite["status"] == "complete" and worlds == suite["world_runs"], "Suite world count")
    require(len(read_csv(output / "all_runs.csv")) == worlds, "Combined summary count")
    result = dict(status="passed", world_runs=worlds, scenarios=len(suite["cases"]),
                  trajectory_files=trajectories, trajectory_rows=records, event_files=event_files,
                  snapshot_hashes_match=True, snapshots_match_current_model=current_matches,
                  scope="provenance and internal consistency; not empirical or substantive validation")
    (output / "validation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    print(json.dumps(validate(parser.parse_args().output), indent=2))
