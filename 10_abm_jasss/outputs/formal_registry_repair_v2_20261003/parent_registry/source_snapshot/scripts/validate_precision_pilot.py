"""Read-only precision-pilot reconstruction, without advancing physical worlds."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from abm_jasss.research_config import ResearchConfig, RESEARCH_VERSION
from abm_jasss.research_replay import PLAN_FIELDS, REPLAY_SCHEMA, rebuild_replay_diagnostics
from abm_jasss.research_world import canonical_hash, jsonable, source_hash
from scripts.precision_artifacts import LOG_FILES, SNAPSHOT_FILE, read, sha256, validate_world_folder
from scripts.precision_statistics import build_precision_analysis
from scripts.run_precision_pilot import CLOSED, E2, PRIMARY, analysis_spec, resolve_design, statistical_records
from scripts.validate_s1_outputs import require, snapshot_state, validate_government

ANALYSIS_SCRIPTS = ("run_precision_pilot.py", "precision_artifacts.py", "precision_statistics.py",
                    "validate_precision_pilot.py", "validate_s1_outputs.py")


def expected_arms(job):
    return [("E2", arm, changes) for arm, changes in E2.items()] + [
        ("E4", arm, changes) for arm, changes in job["branches"].items()] + [
        ("E3_closed", arm, changes) for arm, changes in CLOSED.items()] + [
        ("E3_replay", f"delay{delay}", {"government_delay": delay}) for delay in (0, 1, 3, 10)]


def _prefix_matches(parent, child, context):
    for field in LOG_FILES:
        before = parent["logs"][field]
        after = child["logs"][field][:len(before)]
        if field == "events":
            # Pending plans acquire execution measurements after the boundary.
            before = [{k: v for k, v in e.items()
                       if e["execution_step"] is not None or k not in {"execution_step", "P_execution"}}
                      for e in before]
            after = [{k: e.get(k) for k in old} for old, e in zip(before, after)]
        require(before == after, f"Mother log prefix mismatch: {context}/{field}")


def _unbranched_state(state):
    result = {k: v for k, v in state.items() if k not in {"world_id", "parent_world_id", "snapshot_id"}}
    result["logs"] = {k: v for k, v in state["logs"].items() if k != "treatments"}
    return result


def validate_group(arguments):
    """Keep only a donor, its mother and one endpoint resident per worker."""
    output_name, job, manifest = arguments
    output = Path(output_name)
    group_id = job["group_id"]
    base = ResearchConfig.from_dict(job["model"])
    mother_snapshot = read(output / "mother_snapshots" / f"{group_id}.json.gz")
    mother = snapshot_state(mother_snapshot, manifest, group_id + "/mother")
    require(mother["tick"] == job["fork_tick"] and mother["config"] == jsonable(base.to_dict())
            and mother["seed"] == job["seed"] and mother["parent_world_id"] is None
            and mother["snapshot_id"] is None and not mother["logs"]["treatments"],
            f"Mother snapshot design mismatch: {group_id}")
    require(mother["world_id"] == f"dev-{job['seed']}-{canonical_hash(base.to_dict())[:12]}",
            f"Mother engine identity mismatch: {group_id}")
    parents = {mother_snapshot["state_hash"]: mother_snapshot}
    validate_government(mother, parents, group_id + "/mother")
    donor_name = f"E2_{group_id}_I00"
    donor_snapshot = read(output / "raw" / donor_name / SNAPSHOT_FILE)
    donor = snapshot_state(donor_snapshot, manifest, donor_name)
    require(donor["world_id"] == mother["world_id"] and donor["randomness"] == mother["randomness"]
            and donor["initial_state_hash"] == mother["initial_state_hash"],
            f"Mother/donor identity mismatch: {group_id}")
    _prefix_matches(mother, donor, group_id)
    arms = expected_arms(job)
    expected_ids = [f"{family}_{group_id}_{arm}" for family, arm, _ in arms]
    expected_group = {"group_id": group_id, "run_ids": expected_ids,
                      "checks": {"common_initial_state": True, "common_ordinary_supply": True,
                                 "B0_uninterrupted_equivalence": True, "common_fork_state": True}}
    require(read(output / "groups" / f"{group_id}.json") == expected_group,
            f"Group run inventory/check mismatch: {group_id}")
    records, diagnostics = {}, {}
    trajectory_count = event_count = 0
    for family, arm, changes in arms:
        name = f"{family}_{group_id}_{arm}"
        folder = output / "raw" / name
        derived = validate_world_folder(folder, manifest["source_hash"], parents)
        metadata = read(folder / "metadata.json")
        snapshot = donor_snapshot if name == donor_name else read(folder / SNAPSHOT_FILE)
        state = snapshot["state"]
        config = replace(base, **changes)
        require(metadata["batch_id"] == manifest["batch_id"] and metadata["group_id"] == group_id
                and metadata["scenario"] == family and metadata["condition"] == arm,
                f"World identity/design mismatch: {name}")
        require(state["config"] == jsonable(config.to_dict())
                and metadata["analysis_config"] == jsonable(config.analysis_config()),
                f"World configuration/analysis mismatch: {name}")
        require(state["seed"] == job["seed"] and state["tick"] == base.steps
                and metadata["status"] == "complete" and state["initial_state_hash"] == donor["initial_state_hash"]
                and state["randomness"] == donor["randomness"]
                and state["logs"]["supply_log"] == donor["logs"]["supply_log"],
                f"Unpaired or incomplete pilot world: {name}")
        replay = state["queue"].get("queue_mode") == REPLAY_SCHEMA
        require(replay == (family == "E3_replay"), f"Replay scenario mismatch: {name}")
        if family == "E4":
            require(state["parent_world_id"] == mother["world_id"]
                    and state["snapshot_id"] == mother_snapshot["state_hash"]
                    and len(state["logs"]["treatments"]) == 1,
                    f"E4 mother/fork mismatch: {name}")
            treatment = state["logs"]["treatments"][0]
            require(treatment["branch_id"] == arm and treatment["changes"] == changes
                    and treatment["at"] == job["fork_tick"], f"E4 treatment mismatch: {name}")
            require(metadata["provenance"] == {"mother_snapshot_hash": mother_snapshot["state_hash"],
                                               "fork_tick": job["fork_tick"]},
                    f"E4 provenance mismatch: {name}")
            if arm == "B0":
                require(_unbranched_state(state) == _unbranched_state(donor),
                        f"B0 uninterrupted state mismatch: {name}")
        elif replay:
            queue, plan = state["queue"], state["queue"]["plan"]
            delay = changes["government_delay"]
            require(queue["administrative_delay"] == delay and state["parent_world_id"] is None
                    and state["snapshot_id"] is None
                    and state["world_id"] == f"{donor['world_id']}/replay-delay-{delay}",
                    f"Replay identity/delay mismatch: {name}")
            require(plan["donor_world_id"] == donor["world_id"] and plan["donor_seed"] == donor["seed"]
                    and plan["donor_config"] == donor["config"] and plan["donor_source_hash"] == manifest["source_hash"]
                    and plan["donor_snapshot_hash"] == donor_snapshot["state_hash"]
                    and plan["donor_information_hash"] == canonical_hash(donor["logs"]["information_log"])
                    and plan["events"] == [{k: e[k] for k in PLAN_FIELDS} for e in donor["logs"]["events"]],
                    f"Replay donor reference mismatch: {name}")
            require(metadata["provenance"] == {"donor_run_id": donor_name,
                                               "replay_plan_hash": queue["plan_hash"]},
                    f"Replay provenance mismatch: {name}")
            require(state["logs"]["treatments"] == [{"mode": "controlled_fixed_plan",
                    "plan_hash": queue["plan_hash"], "donor_world_id": donor["world_id"],
                    "administrative_delay": delay,
                    "queue_policy": "fixed donor triggers; no live adaptation or pending-topic filtering"}],
                    f"Replay treatment mismatch: {name}")
            diagnostics[str(delay)] = rebuild_replay_diagnostics(state["logs"]["trajectory"],
                state["logs"]["events"], plan, delay, base.steps)
        else:
            require(not state["logs"]["treatments"] and state["parent_world_id"] is None
                    and state["snapshot_id"] is None and metadata["provenance"] == {}
                    and state["world_id"] == f"dev-{job['seed']}-{canonical_hash(config.to_dict())[:12]}",
                    f"Unexpected closed-world treatment/identity: {name}")
        records[name] = {"family": family, "alpha": job["alpha"], "parent_id": job["seed"],
                         "arm": arm, "metrics": {k: derived["summary"][k] for k in PRIMARY},
                         "status": "complete"}
        trajectory_count += state["tick"]
        event_count += len(state["logs"]["events"])
    require(jsonable(diagnostics) == read(output / "diagnostics" / f"{group_id}.json"),
            f"Replay diagnostic reconstruction mismatch: {group_id}")
    ordered_records = []
    for name in sorted(records):
        record = records[name]
        ordered_records.append(record)
        if name == donor_name:
            ordered_records.append(dict(record, family="E3_closed", arm="baseline"))
    return {"group_id": group_id, "records": ordered_records, "trajectory_records": trajectory_count,
            "response_events": event_count, "initial_state_hash": donor["initial_state_hash"],
            "ordinary_supply_hash": canonical_hash(donor["logs"]["supply_log"]),
            "randomness_hash": canonical_hash(donor["randomness"])}


def validate(output, workers=3):
    require(type(workers) is int and workers >= 1, "Invalid validation worker count")
    output = Path(output)
    require(not output.is_symlink(), "Symlinks are not permitted in an artifact bundle")
    output = output.resolve(strict=True)
    require(output.is_dir(), "Output must be a directory")
    paths = list(output.rglob("*"))
    require(not any(p.is_symlink() for p in paths), "Symlinks are not permitted in an artifact bundle")
    files = {p.relative_to(output).as_posix(): p for p in paths if p.is_file()}
    inventory_path = output / "artifact_hashes.json"
    artifact_inventory_hash = sha256(inventory_path)
    hashes = read(inventory_path)
    require(set(hashes) == set(files) - {"artifact_hashes.json"}, "Artifact file inventory mismatch")
    for relative, digest in hashes.items():
        require(sha256(files[relative]) == digest, f"Artifact hash mismatch: {relative}")
    manifest, spec = read(output / "manifest.json"), read(output / "configuration.json")
    require(manifest["schema_version"] == "precision-batch-1" and manifest["stage"] == "precision_pilot"
            and manifest["formal_ready"] is False and manifest["status"] == "complete"
            and manifest["failed_groups"] == 0 and manifest["code_version"] == RESEARCH_VERSION,
            "Only completed precision-pilot batches can be validated")
    require(spec == manifest["specification"] and canonical_hash(spec) == manifest["specification_hash"]
            and spec["expected_source_hash"] == manifest["source_hash"], "Specification/manifest mismatch")
    launch = read(output / "launch_manifest.json")
    added = {"completed_groups", "failed_groups", "complete_records", "elapsed_seconds"}
    require(set(manifest) == set(launch) | added and launch["status"] == "running"
            and all(launch[k] == manifest[k] for k in launch if k != "status"),
            "Launch/final manifest mismatch")
    archived = {p.name: sha256(p) for p in sorted((output / "source_snapshot" / "abm_jasss").glob("*.py"))}
    require(archived == manifest["source_sha256"] and canonical_hash(archived) == manifest["source_hash"],
            "Archived engine source mismatch")
    require(source_hash() == manifest["source_hash"], "Live engine differs from archived pilot source")
    for name in ANALYSIS_SCRIPTS:
        require(sha256(ROOT / "scripts" / name) == sha256(output / "source_snapshot" / "scripts" / name),
                f"Live analysis source differs from archive: {name}")
    jobs = read(output / "resolved_design.json")
    require(jobs == jsonable(resolve_design(spec, manifest["wave"])), "Resolved pilot design mismatch")
    require(manifest["expected_groups"] == manifest["completed_groups"] == len(jobs)
            and manifest["complete_records"] == 18 * len(jobs) and read(output / "failures.json") == [],
            "Batch completion accounting mismatch")
    group_ids = {j["group_id"] for j in jobs}
    run_ids = {f"{family}_{j['group_id']}_{arm}" for j in jobs for family, arm, _ in expected_arms(j)}
    require({p.name for p in (output / "raw").iterdir() if p.is_dir()} == run_ids
            and not any(p.is_file() for p in (output / "raw").iterdir()), "Raw world inventory mismatch")
    for directory, names in (("derived", {n + ".json" for n in run_ids}),
                             ("groups", {n + ".json" for n in group_ids}),
                             ("diagnostics", {n + ".json" for n in group_ids}),
                             ("mother_snapshots", {n + ".json.gz" for n in group_ids})):
        require({p.name for p in (output / directory).iterdir()} == names,
                f"{directory} artifact inventory mismatch")
    arguments = [(str(output), j, manifest) for j in jobs]
    if workers == 1:
        groups = [validate_group(arg) for arg in arguments]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            groups = list(pool.map(validate_group, arguments))
    # The same seed is deliberately coupled across alpha strata.
    seeds = {}
    for job, group in zip(jobs, groups):
        fingerprint = tuple(group[k] for k in ("initial_state_hash", "ordinary_supply_hash", "randomness_hash"))
        if job["seed"] in seeds:
            require(seeds[job["seed"]] == fingerprint, "Cross-alpha seed pairing mismatch")
        seeds[job["seed"]] = fingerprint
    records = [record for group in groups for record in group["records"]]
    require(records == statistical_records(output, jobs) == read(output / "statistical_records.json"),
            "Statistical record reconstruction mismatch")
    rebuilt = build_precision_analysis(records, analysis_spec(spec, spec[manifest["wave"] + "_seeds"]))
    require(jsonable(rebuilt) == read(output / "precision_analysis.json"),
            "Precision analysis reconstruction mismatch")
    require(source_hash() == manifest["source_hash"], "Engine source changed during validation")
    require(sha256(inventory_path) == artifact_inventory_hash,
            "Artifact inventory changed during validation")
    return {"status": "passed", "stage": "precision_pilot", "formal_ready": False, "read_only": True,
            "output": str(output), "source_hash": manifest["source_hash"],
            "manifest_hash": sha256(output / "manifest.json"),
            "artifact_inventory_hash": artifact_inventory_hash,
            "batch_id": manifest["batch_id"], "wave": manifest["wave"], "hashed_files": len(hashes),
            "groups": len(jobs), "independent_seeds": len(seeds), "world_records": len(run_ids),
            "trajectory_records": sum(g["trajectory_records"] for g in groups),
            "response_events": sum(g["response_events"] for g in groups),
            "derived_rebuilt": True, "replay_diagnostics_rebuilt": True, "precision_analysis_rebuilt": True,
            "scope": "Archived integrity, legal decisions, lineage and precision planning; no physical simulation or formal release"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    try:
        result = validate(args.output, args.workers)
    except (ValueError, TypeError, KeyError, IndexError, OSError) as error:
        print(json.dumps({"status": "failed", "read_only": True, "error": str(error)}, ensure_ascii=False))
        raise SystemExit(1)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
