"""Recover a finalized formal batch into a new, repaired-registry batch.

Successful whole groups copy raw bytes and rebuild summaries without creating worlds.
Failed/missing groups rerun all 18 endpoints using their original frozen job.
All original artifacts remain unchanged; recovery never adds independent seeds.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import filecmp
from pathlib import Path
import platform
import shutil
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
from abm_jasss.research_replay import REPLAY_SCHEMA
from abm_jasss.research_world import canonical_hash, jsonable
from scripts import formal_artifacts as artifacts
from scripts import formal_runtime as runtime
from scripts import run_formal_study as entry
from scripts.formal_registry import validate_registry, resolve_formal_design
from scripts.validate_s1_outputs import require


def _original_batch(source):
    """Read complete final inventory before any recovery output is created."""
    source = Path(source).resolve(strict=True)
    inventory_hash, file_count = entry._check_inventory(source)
    registry = source / "registry"
    gate = validate_registry(registry, check_live=False)
    manifest = artifacts.read(source / "manifest.json")
    launch = artifacts.read(source / "launch_manifest.json")
    spec = artifacts.read(source / "configuration.json")
    failures = artifacts.read(source / "failures.json")
    require(manifest.get("schema_version") == "formal-batch-1" and manifest.get("stage") == "formal"
            and manifest.get("formal_ready") is True and manifest.get("status") in ("complete", "failed")
            and manifest.get("code_version") == RESEARCH_VERSION, "Original batch is not finalized")
    added = {"completed_groups", "failed_groups", "complete_records", "elapsed_seconds"}
    require(set(manifest) == set(launch) | added and launch.get("status") == "running"
            and all(launch[k] == manifest[k] for k in launch if k != "status"), "Original launch/final mismatch")
    require(spec == artifacts.read(registry / "configuration.json") == manifest["specification"]
            and canonical_hash(spec) == manifest["specification_hash"] == gate["specification_hash"]
            and manifest["registry_hash"] == gate["registry_hash"]
            and manifest["source_hash"] == gate["source_hash"], "Original registry binding mismatch")
    jobs = jsonable(resolve_formal_design(spec))
    require(jobs == artifacts.read(source / "resolved_design.json")
            == artifacts.read(registry / "resolved_design.json"), "Original job registry mismatch")
    group_ids = {job["group_id"] for job in jobs}
    require(len(group_ids) == len(jobs) == manifest["expected_groups"], "Original group count mismatch")
    require(isinstance(failures, list) and len(failures) == manifest["failed_groups"]
            and all(isinstance(f, dict) and f.get("group_id") in group_ids | {"batch_finalization"}
                    and isinstance(f.get("traceback"), str) for f in failures), "Original failure inventory mismatch")
    require((manifest["status"] == "complete") == (not failures), "Original status/failure mismatch")
    complete_groups = {}
    folder = source / "groups"
    if folder.exists():
        require(all(p.is_file() and p.suffix == ".json" for p in folder.iterdir()), "Invalid original group inventory")
        for path in folder.iterdir():
            require(path.stem in group_ids, "Unregistered original group")
            complete_groups[path.stem] = artifacts.read(path)
    require(len(complete_groups) == manifest["completed_groups"]
            and manifest["complete_records"] == 18 * len(complete_groups), "Original completion accounting mismatch")
    if manifest["status"] == "complete":
        require(set(complete_groups) == group_ids, "Complete original batch has missing groups")
    failed_groups = {f["group_id"] for f in failures} & group_ids
    inventory = artifacts.read(source / "artifact_hashes.json")
    for job in jobs:
        group_id = job["group_id"]
        if group_id not in complete_groups:
            continue
        expected_ids = [f"{family}_{group_id}_{arm}" for family, arm, _ in runtime.expected_arms(job)]
        require(complete_groups[group_id] == {"group_id": group_id, "run_ids": expected_ids,
            "checks": {"common_initial_state": True, "common_ordinary_supply": True,
                       "B0_uninterrupted_equivalence": True, "common_fork_state": True}},
                "Original complete group inventory/checks mismatch")
        require(all(f"raw/{run_id}/metadata.json" in inventory and f"derived/{run_id}.json" in inventory
                    for run_id in expected_ids)
                and all(f"{name}/{group_id}{suffix}" in inventory for name, suffix in
                    (("mother_snapshots", ".json.gz"), ("diagnostics", ".json"))),
                "Original successful group has missing artifacts")
    return source, gate, manifest, spec, jobs, inventory_hash, inventory, complete_groups, failed_groups, file_count


def _job_source_files(job, inventory):
    group = job["group_id"]
    names = {f"{folder}/{group}{suffix}" for folder, suffix in
             (("groups", ".json"), ("diagnostics", ".json"), ("mother_snapshots", ".json.gz"))}
    run_ids = [f"{family}_{group}_{arm}" for family, arm, _ in runtime.expected_arms(job)]
    names.update(f"derived/{run_id}.json" for run_id in run_ids)
    raw_names = {artifacts.SNAPSHOT_FILE, artifacts.ACTIONS_FILE, *artifacts.LOG_FILES.values(), "metadata.json"}
    names.update(f"raw/{run_id}/{relative}" for run_id in run_ids for relative in raw_names)
    return {name: inventory[name] for name in sorted(names) if name in inventory}


def _copy_endpoint(job, source, output, manifest, original_manifest, binding, family, arm, source_files):
    """Copy registered raw bytes and rebuild metadata/derived from a pure snapshot.

    No World constructor or restoration is needed. Full physical semantics are
    still reconstructed by the unchanged validate_batch before any analysis.
    """
    group, run_id = job["group_id"], f"{family}_{job['group_id']}_{arm}"
    old_folder, folder = source / "raw" / run_id, output / "raw" / run_id
    derived_path = output / "derived" / f"{run_id}.json"
    require(not folder.exists() and not derived_path.exists(), "Recovery world output must not exist")
    old_metadata = artifacts.read(old_folder / "metadata.json")
    require(artifacts.sha256(old_folder / "metadata.json") == source_files.get(f"raw/{run_id}/metadata.json"),
            "Original metadata changed during recovery")
    require(old_metadata["batch_id"] == original_manifest["batch_id"]
            and old_metadata["formal_registry_hash"] == original_manifest["registry_hash"]
            and old_metadata["formal_specification_hash"] == original_manifest["specification_hash"]
            and old_metadata["formal_job_hash"] == canonical_hash(job)
            and old_metadata["source_hash"] == manifest["source_hash"]
            and old_metadata["group_id"] == group and old_metadata["scenario"] == family
            and old_metadata["condition"] == arm and old_metadata["status"] == "complete",
            "Original world metadata binding mismatch")
    raw_names = {artifacts.SNAPSHOT_FILE, artifacts.ACTIONS_FILE, *artifacts.LOG_FILES.values()}
    raw_hashes = old_metadata["raw_sha256"]
    require(set(raw_hashes) == raw_names and all(raw_hashes[name] == source_files.get(f"raw/{run_id}/{name}")
            for name in raw_names), "Original raw metadata inventory mismatch")
    require({p.relative_to(old_folder).as_posix() for p in old_folder.rglob("*") if p.is_file()}
            == raw_names | {"metadata.json"}, "Original endpoint contains unexpected files")
    snapshot = artifacts.read(old_folder / artifacts.SNAPSHOT_FILE)
    state = artifacts.snapshot_state(snapshot, manifest, run_id)
    require((state["queue"].get("queue_mode") == REPLAY_SCHEMA) == (family == "E3_replay"),
            "Original replay type mismatch")
    require(old_metadata["analysis_config"] == artifacts._analysis_config(state, None),
            "Original analysis configuration differs from the registered world")
    # _metadata enforces the validated job capability, exact allowed scenario /
    # configuration, registered seed, source and complete terminal tick. Its
    # remaining fields bind the snapshot, engine identities and every log hash.
    metadata = artifacts._metadata(snapshot, manifest["batch_id"], run_id, group, family, arm,
        manifest["source_hash"], old_metadata["analysis_config"], old_metadata["provenance"], raw_hashes, binding)
    old_batch = original_manifest["batch_id"]
    old_expected = dict(metadata, batch_id=old_batch, world_id=f"{old_batch}/{run_id}",
        parent_world_id=None if state["parent_world_id"] is None else f"{old_batch}/engine/{state['parent_world_id']}",
        engine_reference_id=f"{old_batch}/engine/{state['world_id']}",
        formal_registry_hash=original_manifest["registry_hash"])
    require(old_expected == old_metadata, "Original metadata does not reconstruct from its snapshot and job")
    derived = jsonable(artifacts.build_formal_derived(state, metadata))
    artifacts._json_bytes(metadata)
    artifacts._json_bytes(derived)
    folder.mkdir(parents=True, exist_ok=False)
    proof = {}
    for relative in sorted(raw_names):
        name = f"raw/{run_id}/{relative}"
        target = output / name
        require(artifacts.sha256(source / name) == source_files[name], "Original raw changed during recovery")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
        require(artifacts.sha256(target) == source_files[name]
                and filecmp.cmp(source / name, target, shallow=False), "Recovery changed original raw bytes: " + name)
        proof[name] = source_files[name]
    artifacts.write_json(folder / "metadata.json", metadata)
    artifacts.write_json(derived_path, derived)
    return proof


def recover_group(job, source_name, output_name, manifest, original_manifest, registry, reuse, source_files):
    source, output = Path(source_name), Path(output_name)
    group = job["group_id"]
    binding = runtime._authorize(registry, job, manifest["source_hash"])
    copied, raw_proofs = [], {}
    if reuse:
        for family, arm, _ in runtime.expected_arms(job):
            raw_proofs.update(_copy_endpoint(job, source, output, manifest, original_manifest,
                                            binding, family, arm, source_files))
        for folder, suffix in (("mother_snapshots", ".json.gz"), ("diagnostics", ".json"), ("groups", ".json")):
            name = f"{folder}/{group}{suffix}"
            target = output / name
            require(not target.exists() and artifacts.sha256(source / name) == source_files[name],
                    "Original group evidence changed")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, target)
            require(artifacts.sha256(target) == source_files[name] and filecmp.cmp(source / name, target, shallow=False),
                    "Copied group evidence differs")
            copied.append(name)
        result = artifacts.read(output / "groups" / f"{group}.json")
    else:
        result = runtime.run_group(job, str(output), manifest["batch_id"], manifest["source_hash"], registry)
    proof = {"group_id": group, "job_hash": canonical_hash(job), "seed": job["seed"], "alpha": job["alpha"],
        "mode": "raw_copied_without_world_construction" if reuse else "entire_original_group_rerun",
        "world_construction_or_restore_used": not reuse, "physical_world_steps_executed": 0 if reuse else None,
        "independent_samples_added": 0, "source_batch_id": original_manifest["batch_id"],
        "source_inventory_hash": manifest["recovery"]["source_inventory_hash"],
        "source_files_sha256": source_files, "unchanged_raw_gzip_sha256": raw_proofs,
        "copied_group_evidence": copied, "new_endpoint_count": len(result["run_ids"]),
        "raw_bytes_verified": reuse}
    artifacts.write_json(output / "recovery_groups" / f"{group}.json", proof)
    return result


def recover_study(source, registry, output, workers=3):
    require(type(workers) is int and workers >= 1, "Invalid workers")
    output = entry._new_directory(output, [source, registry])
    source, old_gate, old_manifest, spec, jobs, old_inventory_hash, inventory, completed, failed, file_count = _original_batch(source)
    registry = Path(registry).resolve(strict=True)
    gate = validate_registry(registry)
    require(artifacts.read(registry / "configuration.json") == spec
            and artifacts.read(registry / "resolved_design.json") == jobs
            and gate["source_hash"] == old_gate["source_hash"], "Repair changed the frozen physical design")
    context = artifacts.read(registry / "repair_context.json")
    require(context.get("parent_registry_hash") == old_gate["registry_hash"]
            and context.get("additional_independent_samples") == 0,
            "Repair registry does not authorize this original registry without new samples")
    reusable = set(completed) - failed
    output.mkdir(parents=True, exist_ok=False)
    shutil.copytree(registry, output / "registry")
    local_registry = output / "registry"
    copied_gate = validate_registry(local_registry)
    require(copied_gate["registry_hash"] == gate["registry_hash"], "Copied repair registry differs")
    # Archive original completion/failure evidence verbatim; original raw remains
    # immutable in source, and reused raw is proven byte-identical below.
    for name in ("configuration.json", "resolved_design.json", "launch_manifest.json", "manifest.json",
                 "failures.json", "artifact_hashes.json"):
        destination = output / "recovery_source" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, destination)
    shutil.copytree(source / "registry", output / "recovery_source/registry")
    started = time.monotonic()
    recovery = {"source_path": str(source), "source_batch_id": old_manifest["batch_id"],
        "source_status": old_manifest["status"], "source_inventory_hash": old_inventory_hash,
        "source_manifest_hash": artifacts.sha256(source / "manifest.json"),
        "source_registry_hash": old_gate["registry_hash"], "source_hashed_files": file_count,
        "planned_reused_groups": len(reusable), "planned_rerun_groups": len(jobs) - len(reusable),
        "additional_independent_samples": 0, "unchanged_design": True}
    manifest = {"schema_version": "formal-batch-1", "stage": "formal", "formal_ready": True,
        "status": "running", "batch_id": "formal_recovered_" + uuid.uuid4().hex,
        "created_at": datetime.now(timezone.utc).isoformat(), "workers": workers,
        "code_version": RESEARCH_VERSION, "source_hash": gate["source_hash"], "registry_hash": gate["registry_hash"],
        "specification_hash": canonical_hash(spec), "specification": spec, "expected_groups": len(jobs),
        "python": platform.python_version(), "numpy": np.__version__, "recovery": recovery}
    artifacts.write_json(output / "configuration.json", spec)
    artifacts.write_json(output / "resolved_design.json", jobs)
    artifacts.write_json(output / "launch_manifest.json", manifest)
    results, failures = [], []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        pending = {pool.submit(recover_group, job, str(source), str(output), manifest, old_manifest,
                    str(local_registry), job["group_id"] in reusable, _job_source_files(job, inventory)): job for job in jobs}
        for future in as_completed(pending):
            job = pending[future]
            try:
                results.append(future.result())
                print(f"recovery: {len(results)}/{len(jobs)} complete {job['group_id']}", flush=True)
            except Exception:
                failures.append({"group_id": job["group_id"], "traceback": traceback.format_exc()})
                print(f"recovery: FAILED {job['group_id']}", flush=True)
    try:
        require(entry._check_inventory(source)[0] == old_inventory_hash, "Original batch changed during recovery")
        validate_registry(local_registry)
        if not failures:
            artifacts.write_json(output / "statistical_records.json", entry.statistical_records(output, jobs))
            artifacts.write_json(output / "auxiliary_records.json", entry.auxiliary_records(output, jobs))
    except Exception:
        failures.append({"group_id": "batch_finalization", "traceback": traceback.format_exc()})
    artifacts.write_json(output / "recovery_provenance.json", {**recovery,
        "new_registry_hash": gate["registry_hash"], "new_batch_id": manifest["batch_id"],
        "completed_groups": len(results), "failed_groups": len(failures),
        "recovery_group_sha256": {path.stem: artifacts.sha256(path)
            for path in sorted((output / "recovery_groups").glob("*.json"))},
        "source_status_is_not_rewritten": True})
    artifacts.write_json(output / "failures.json", failures)
    manifest.update(status="failed" if failures else "complete", completed_groups=len(results),
        failed_groups=len(failures), complete_records=sum(len(result["run_ids"]) for result in results),
        elapsed_seconds=time.monotonic() - started)
    artifacts.write_json(output / "manifest.json", manifest)
    entry._write_inventory(output)
    require(not failures, "Formal recovery failed; original and recovery evidence preserved")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("registry", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", default=3, type=int)
    args = parser.parse_args()
    try:
        result = recover_study(args.source, args.registry, args.output, args.workers)
    except (ValueError, TypeError, KeyError, OSError, ArithmeticError) as error:
        print(artifacts._json_bytes({"status": "failed", "error": str(error)}).decode(), end="")
        raise SystemExit(1)
    print(artifacts._json_bytes(result).decode(), end="")


if __name__ == "__main__":
    main()
