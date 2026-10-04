"""Guarded formal execution, read-only reconstruction and new-output analysis.

The plan command never constructs a world. Every run uses the entire frozen
registry; there is no sample-size, seed, treatment or precision override.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import csv
import json
from pathlib import Path
import platform
import shutil
import statistics
import sys
import time
import traceback
import uuid

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
from abm_jasss.research_config import RESEARCH_VERSION
from abm_jasss.research_world import canonical_hash, jsonable
from scripts.precision_artifacts import read, write_json, sha256
from scripts.run_precision_pilot import statistical_records
from scripts.validate_precision_pilot import expected_arms
from scripts.validate_s1_outputs import require
from scripts.formal_inference import build_formal_inference
from scripts.formal_registry import validate_registry, resolve_formal_design, inference_spec

SUMMARY_AUXILIARY = (
    "has_response", "execution_count", "execution_coverage", "scheduled_count",
    "pending_count", "waiting_time", "response_completion_L", "exposure_gap",
    "targeting_error_execution",
)
MECHANISM_AUXILIARY = ("final_preference_shift", "final_trust_mean", "max_pending")


def _new_directory(path, inputs=()):
    path = Path(path).resolve()
    require(not path.exists(), "Output already exists; preserve immutable artifacts")
    require(all(not path.is_relative_to(Path(p).resolve()) for p in inputs),
            "Output cannot be inside an immutable input")
    return path


def _write_inventory(output):
    write_json(output / "artifact_hashes.json", {
        p.relative_to(output).as_posix(): sha256(p)
        for p in sorted(output.rglob("*")) if p.is_file()
    })


def _check_inventory(output):
    output = Path(output)
    require(output.is_dir() and not output.is_symlink(), "Invalid artifact directory")
    paths = list(output.rglob("*"))
    require(not any(p.is_symlink() for p in paths), "Symlinks are not permitted")
    files = {p.relative_to(output).as_posix(): p for p in paths if p.is_file()}
    digest = sha256(output / "artifact_hashes.json")
    inventory = read(output / "artifact_hashes.json")
    require(set(inventory) == set(files) - {"artifact_hashes.json"}, "Artifact inventory mismatch")
    for name, expected in inventory.items():
        require(sha256(files[name]) == expected, f"Artifact hash mismatch: {name}")
    require(sha256(output / "artifact_hashes.json") == digest, "Inventory changed while reading")
    return digest, len(inventory)


def plan(registry):
    gate = validate_registry(registry)
    spec = read(Path(registry) / "configuration.json")
    jobs = resolve_formal_design(spec)
    return {"status": "ready", "stage": "formal_plan", "formal_ready": True,
            "registry_hash": gate["registry_hash"], "source_hash": gate["source_hash"],
            "sample_sizes": spec["sample_sizes"], "independent_seeds": len(spec["seeds"]),
            "groups": len(jobs), "world_records": 18 * len(jobs),
            "statistical_arms": 19 * len(jobs), "models_executed": 0,
            "scope": "Frozen E2/E3/E4 design; no dynamic or empirical study release"}


def auxiliary_records(output, jobs):
    records = []
    for job in jobs:
        for family, arm, _ in expected_arms(job):
            name = f"{family}_{job['group_id']}_{arm}"
            derived = read(Path(output) / "derived" / (name + ".json"))
            summary, mechanisms = derived["summary"], derived["mechanisms"]
            values = {key: summary[key] for key in SUMMARY_AUXILIARY}
            values.update({key: mechanisms[key] for key in MECHANISM_AUXILIARY})
            values.update(platform_signal_coverage=summary["metric_coverage"]["platform_representation_gap"]["coverage"],
                          perception_data_coverage=summary["metric_coverage"]["perception_error"]["coverage"])
            record = {"family": family, "arm": arm, "alpha": job["alpha"],
                      "parent_id": job["seed"], "values": values}
            records.append(record)
            if family == "E2" and arm == "I00":
                records.append(dict(record, family="E3_closed", arm="baseline"))
    return records


def run_study(registry, output, workers=3):
    from scripts.formal_runtime import run_group
    require(type(workers) is int and workers >= 1, "Invalid workers")
    registry = Path(registry).resolve()
    output = _new_directory(output, [registry])
    gate = validate_registry(registry)
    spec = read(registry / "configuration.json")
    jobs = jsonable(resolve_formal_design(spec))
    output.mkdir(parents=True, exist_ok=False)
    shutil.copytree(registry, output / "registry")
    local_registry = output / "registry"
    copied = validate_registry(local_registry)
    require(copied["registry_hash"] == gate["registry_hash"], "Copied registry differs")
    started = time.monotonic()
    manifest = {
        "schema_version": "formal-batch-1", "stage": "formal", "formal_ready": True,
        "status": "running", "batch_id": "formal_" + uuid.uuid4().hex,
        "created_at": datetime.now(timezone.utc).isoformat(), "workers": workers,
        "code_version": RESEARCH_VERSION, "source_hash": gate["source_hash"],
        "registry_hash": gate["registry_hash"], "specification_hash": canonical_hash(spec),
        "specification": spec, "expected_groups": len(jobs),
        "python": platform.python_version(), "numpy": np.__version__,
    }
    write_json(output / "configuration.json", spec)
    write_json(output / "resolved_design.json", jobs)
    write_json(output / "launch_manifest.json", manifest)
    results, failures = [], []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        pending = {pool.submit(run_group, job, str(output), manifest["batch_id"],
                               manifest["source_hash"], str(local_registry)): job for job in jobs}
        for future in as_completed(pending):
            job = pending[future]
            try:
                results.append(future.result())
                print(f"formal: {len(results)}/{len(jobs)} complete {job['group_id']}", flush=True)
            except Exception:
                failures.append({"group_id": job["group_id"], "traceback": traceback.format_exc()})
                print(f"formal: FAILED {job['group_id']}", flush=True)
    try:
        validate_registry(local_registry)
        if not failures:
            write_json(output / "statistical_records.json", statistical_records(output, jobs))
            write_json(output / "auxiliary_records.json", auxiliary_records(output, jobs))
    except Exception:
        failures.append({"group_id": "batch_finalization", "traceback": traceback.format_exc()})
    write_json(output / "failures.json", failures)
    manifest.update(status="failed" if failures else "complete", completed_groups=len(results),
                    failed_groups=len(failures), complete_records=sum(len(r["run_ids"]) for r in results),
                    elapsed_seconds=time.monotonic() - started)
    write_json(output / "manifest.json", manifest)
    _write_inventory(output)
    require(not failures, "Formal batch failed; raw and failures retained; inference not released")
    return manifest


def _registered_batch(output):
    output = Path(output).resolve(strict=True)
    digest, count = _check_inventory(output)
    registry = output / "registry"
    gate = validate_registry(registry)
    manifest = read(output / "manifest.json")
    spec = read(output / "configuration.json")
    require(manifest["schema_version"] == "formal-batch-1" and manifest["stage"] == "formal"
            and manifest["formal_ready"] is True and manifest["status"] == "complete"
            and manifest["failed_groups"] == 0 and manifest["code_version"] == RESEARCH_VERSION,
            "Only complete formal batches can be accepted")
    require(spec == read(registry / "configuration.json") == manifest["specification"]
            and canonical_hash(spec) == manifest["specification_hash"] == gate["specification_hash"]
            and manifest["registry_hash"] == gate["registry_hash"]
            and manifest["source_hash"] == gate["source_hash"], "Formal registry binding mismatch")
    launch = read(output / "launch_manifest.json")
    added = {"completed_groups", "failed_groups", "complete_records", "elapsed_seconds"}
    require(set(manifest) == set(launch) | added and launch["status"] == "running"
            and all(launch[k] == manifest[k] for k in launch if k != "status"),
            "Launch/final manifest mismatch")
    jobs = jsonable(resolve_formal_design(spec))
    require(jobs == read(output / "resolved_design.json")
            == read(registry / "resolved_design.json"), "Formal resolved design mismatch")
    require(manifest["expected_groups"] == manifest["completed_groups"] == len(jobs)
            and manifest["complete_records"] == 18 * len(jobs)
            and read(output / "failures.json") == [], "Formal completion accounting mismatch")
    return output, registry, gate, manifest, spec, jobs, digest, count


def validate_batch(output, workers=3):
    from scripts.formal_runtime import validate_group
    require(type(workers) is int and workers >= 1, "Invalid workers")
    output, registry, gate, manifest, spec, jobs, digest, count = _registered_batch(output)
    run_ids = {f"{family}_{j['group_id']}_{arm}" for j in jobs
               for family, arm, _ in expected_arms(j)}
    group_ids = {j["group_id"] for j in jobs}
    require({p.name for p in (output / "raw").iterdir() if p.is_dir()} == run_ids
            and not any(p.is_file() for p in (output / "raw").iterdir()), "Raw run inventory mismatch")
    for folder, expected in (("derived", {s + ".json" for s in run_ids}),
                             ("groups", {s + ".json" for s in group_ids}),
                             ("diagnostics", {s + ".json" for s in group_ids}),
                             ("mother_snapshots", {s + ".json.gz" for s in group_ids})):
        require({p.name for p in (output / folder).iterdir()} == expected,
                f"Formal {folder} inventory mismatch")
    arguments = [(str(output), j, manifest, str(registry)) for j in jobs]
    if workers == 1:
        groups = [validate_group(arg) for arg in arguments]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            groups = list(pool.map(validate_group, arguments))
    fingerprints = {}
    for job, group in zip(jobs, groups):
        value = tuple(group[key] for key in ("initial_state_hash", "ordinary_supply_hash", "randomness_hash"))
        if job["seed"] in fingerprints:
            require(fingerprints[job["seed"]] == value, "Cross-alpha pairing mismatch")
        fingerprints[job["seed"]] = value
    records = [record for group in groups for record in group["records"]]
    require(records == statistical_records(output, jobs) == read(output / "statistical_records.json"),
            "Formal statistical reconstruction mismatch")
    require(auxiliary_records(output, jobs) == read(output / "auxiliary_records.json"),
            "Formal auxiliary reconstruction mismatch")
    require(sha256(output / "artifact_hashes.json") == digest, "Artifact inventory changed during validation")
    validate_registry(registry)
    return {"status": "passed", "read_only": True, "stage": "formal", "formal_ready": True,
            "batch_id": manifest["batch_id"], "registry_hash": gate["registry_hash"],
            "source_hash": gate["source_hash"], "manifest_hash": sha256(output / "manifest.json"),
            "artifact_inventory_hash": digest, "hashed_files": count,
            "groups": len(jobs), "independent_seeds": len(fingerprints), "world_records": len(run_ids),
            "trajectory_records": sum(g["trajectory_records"] for g in groups),
            "response_events": sum(g["response_events"] for g in groups),
            "derived_rebuilt": True, "statistical_records_rebuilt": True,
            "auxiliary_records_rebuilt": True, "replay_diagnostics_rebuilt": True}


def _primary_rows(inference):
    rows = []
    for group in inference["groups"]:
        for contrast, metrics in group["contrasts"].items():
            for metric, item in metrics.items():
                interval = item["confidence_interval"]
                rows.append({"family": group["family"], "alpha": group["alpha"],
                    "contrast": contrast, "metric": metric, "status": item["status"],
                    **{key: item[key] for key in ("n_total", "n_joint_valid", "n_single_sided_valid",
                        "n_partially_valid", "n_none_valid", "mean", "sample_sd", "standard_error",
                        "degrees_of_freedom", "confidence_half_width", "p_value_two_sided", "p_value_holm", "p_value_numerical_floor",
                        "reject_holm_0_05", "observed_target_half_width_met")},
                    "ci_lower": interval[0] if interval else None,
                    "ci_upper": interval[1] if interval else None})
    return rows


def _auxiliary_rows(records):
    grouped = {}
    for record in records:
        for metric, value in record["values"].items():
            key = record["family"], record["alpha"], record["arm"], metric
            grouped.setdefault(key, []).append(value)
    return [{"family": key[0], "alpha": key[1], "arm": key[2], "metric": key[3],
             "n_total": len(values), "n_valid": len(observed),
             "mean": statistics.mean(observed) if observed else None,
             "scope": "descriptive_equal_weight_mother_world_means"}
            for key, values in sorted(grouped.items())
            for observed in [[float(v) for v in values if v is not None]]]


def _write_csv(path, rows):
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def analyze_batch(batch, output, validation):
    output = _new_directory(output, [batch])
    batch, registry, gate, manifest, spec, jobs, digest, _ = _registered_batch(batch)
    report = read(Path(validation))
    require(report.get("status") == "passed" and report.get("read_only") is True
            and report.get("stage") == "formal" and report.get("formal_ready") is True,
            "Formal semantic validation report did not pass")
    for key, value in (("batch_id", manifest["batch_id"]), ("registry_hash", gate["registry_hash"]),
                       ("source_hash", gate["source_hash"]), ("manifest_hash", sha256(batch / "manifest.json")),
                       ("artifact_inventory_hash", digest)):
        require(report.get(key) == value, f"Stale or mismatched formal validation: {key}")
    require(all(report.get(key) is True for key in
                ("derived_rebuilt", "statistical_records_rebuilt", "auxiliary_records_rebuilt", "replay_diagnostics_rebuilt")),
            "Missing semantic reconstruction evidence")
    records = read(batch / "statistical_records.json")
    require(len(records) == 19 * len(jobs), "Incomplete formal statistical records")
    inference = build_formal_inference(records, inference_spec(spec))
    require(inference["operationally_complete"], "Operational gaps prevent formal analysis release")
    rows = _primary_rows(inference)
    auxiliary = _auxiliary_rows(read(batch / "auxiliary_records.json"))
    estimated = sum(row["status"] == "estimated" for row in rows)
    precise = sum(row["observed_target_half_width_met"] is True for row in rows)
    analysis_manifest = {"schema_version": "formal-analysis-1", "stage": "formal_analysis",
        "created_at": datetime.now(timezone.utc).isoformat(), "formal_ready": True,
        "batch_id": manifest["batch_id"], "registry_hash": gate["registry_hash"],
        "source_hash": gate["source_hash"], "specification_hash": canonical_hash(spec),
        "manifest_hash": sha256(batch / "manifest.json"), "artifact_inventory_hash": digest,
        "validation_report_hash": sha256(validation), "comparison_count": len(rows),
        "semantic_validation_complete": True, "additional_sampling": False}
    text = ("# Frozen formal E2/E3/E4 analysis\n\n"
        f"All {len(jobs)} registered alpha-by-seed blocks completed; {len(spec['seeds'])} independent seeds. "
        f"{len(rows)} registered comparisons; {estimated} with available inference; "
        f"{precise} observed pointwise half-widths at most 0.02.\n\n"
        "Estimates condition on comparison-specific joint support. Intervals are pointwise Student t95; "
        "two-sided p values use Holm across all 102 comparisons. Approximate marginal t inference also "
        "makes familywise error control approximate; these intervals are not simultaneous. Undefined "
        "tests retain a slot with internal p=1. No result authorizes additional seeds.\n\n"
        "The user retained the 1000-seed cap and accepted three pilot planning shortfalls; all 61 pilot "
        "variance-instability flags remain in the frozen registry. Observed precision is reported without "
        "retrospective sample-size or hypothesis changes.\n\n"
        "See primary.csv for all comparisons; inference.json for parent-level contrasts and missingness; "
        "auxiliary.csv for response incidence, counts, waiting, completion and mechanism descriptions. "
        "Secondary descriptions do not form additional confirmatory tests.\n")
    require(sha256(batch / "artifact_hashes.json") == digest, "Input inventory changed during analysis")
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "inference.json", inference)
    write_json(output / "analysis_manifest.json", analysis_manifest)
    _write_csv(output / "primary.csv", rows)
    _write_csv(output / "auxiliary.csv", auxiliary)
    with (output / "report.md").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
    _write_inventory(output)
    return analysis_manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("plan")
    command.add_argument("registry", type=Path)
    command = commands.add_parser("run")
    command.add_argument("registry", type=Path)
    command.add_argument("--output", required=True, type=Path)
    command.add_argument("--workers", default=3, type=int)
    command = commands.add_parser("validate")
    command.add_argument("output", type=Path)
    command.add_argument("--workers", default=3, type=int)
    command = commands.add_parser("analyze")
    command.add_argument("batch", type=Path)
    command.add_argument("--output", required=True, type=Path)
    command.add_argument("--validation", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "plan":
            result = plan(args.registry)
        elif args.command == "run":
            result = run_study(args.registry, args.output, args.workers)
        elif args.command == "validate":
            result = validate_batch(args.output, args.workers)
        else:
            result = analyze_batch(args.batch, args.output, args.validation)
    except (ValueError, TypeError, KeyError, OSError, ArithmeticError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        raise SystemExit(1)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
