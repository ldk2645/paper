"""Registered formal group execution and read-only reconstruction.

Physical group semantics remain those accepted in the independent pilot:
18 endpoints and 19 statistical arms, with I00 reused as E3 baseline. Public
entry points validate a frozen registry path; they never accept a Boolean
formal flag or a caller-provided validation dictionary as authorization.
"""
from dataclasses import replace
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from abm_jasss.research_config import ResearchConfig, RESEARCH_VERSION
from abm_jasss.research_replay import PLAN_FIELDS, REPLAY_SCHEMA, rebuild_replay_diagnostics
from abm_jasss.research_world import ResearchWorld, canonical_hash, jsonable, source_hash
from scripts.formal_artifacts import (LOG_FILES, SNAPSHOT_FILE, read, sha256,
    validate_world_folder, write_json, _validated_binding)
from scripts.run_precision_pilot import E2, CLOSED, PRIMARY, statistical_records
from scripts.validate_s1_outputs import require, snapshot_state, validate_government

_REGISTRY_CACHE = {}
_REGISTRY_FILES = ("manifest.json", "artifact_hashes.json", "configuration.json", "resolved_design.json")


def _registry_fingerprints(registry):
    require(registry.is_dir() and not registry.is_symlink(), "Expected a real formal registry directory")
    fingerprints = {}
    for name in _REGISTRY_FILES:
        path = registry / name
        require(path.is_file() and not path.is_symlink(), f"Missing or unsafe registry file: {name}")
        fingerprints[name] = sha256(path)
    return fingerprints


def _validate_registry(registry):
    from scripts.formal_registry import validate_registry
    return validate_registry(registry)


def _authorize(registry, job, expected_hash):
    """Full registry audit once per process; bind key files and exact job every time.

    The batch entry point additionally audits all archived/live sources at
    start and finish. No persistent trusted flag is written to the registry.
    """
    require(isinstance(registry, (str, Path)), "A formal registry path is required")
    path = Path(registry)
    require(not path.is_symlink(), "Registry symlinks are not permitted")
    path = path.resolve(strict=True)
    fingerprints = _registry_fingerprints(path)
    key = str(path)
    if key not in _REGISTRY_CACHE:
        report = _validate_registry(path)
        require(report.get("status") == "passed" and report.get("formal_ready") is True,
                "Formal registry validation did not pass")
        require(report["registry_hash"] == fingerprints["manifest.json"] and
                report["specification_hash"] == canonical_hash(read(path / "configuration.json")),
                "Formal registry validation binding mismatch")
        jobs = read(path / "resolved_design.json")
        require(isinstance(jobs, list) and jobs, "Empty formal registry job list")
        registered = {}
        for item in jobs:
            require(item["group_id"] not in registered, "Duplicate formal registry group")
            registered[item["group_id"]] = canonical_hash(item)
        require(_registry_fingerprints(path) == fingerprints, "Formal registry changed during validation")
        _REGISTRY_CACHE[key] = (fingerprints, report, registered)
    previous, report, registered = _REGISTRY_CACHE[key]
    require(fingerprints == previous, "Formal registry changed after validation")
    require(expected_hash == report["source_hash"] == source_hash(), "Formal engine source mismatch")
    require(isinstance(job, dict) and registered.get(job.get("group_id")) == canonical_hash(job),
            "Job is not in the validated formal registry")
    return _validated_binding(report, job)


def run_group(job, output_name, batch_id, expected_hash, registry):
    from scripts.formal_artifacts import save_world, write_gzip_json
    from abm_jasss.research_replay import make_replay_worlds, replay_diagnostics
    binding = _authorize(registry, job, expected_hash)
    output = Path(output_name)
    require(not any(path.is_symlink() for path in (output, output / "mother_snapshots",
            output / "groups", output / "diagnostics")), "Symlinks are not permitted in a formal batch")
    require(source_hash() == expected_hash, "Engine changed before worker start")
    cfg = ResearchConfig.from_dict(job["model"])
    donor = ResearchWorld(cfg, job["seed"]).run(until=job["fork_tick"])
    mother = donor.snapshot()
    write_gzip_json(output / "mother_snapshots" / (job["group_id"] + ".json.gz"), mother)
    donor.run()
    run_ids = []

    def save(world, family, arm, provenance=None):
        require(world.initial_state_hash == donor.initial_state_hash, "Paired initial arrays differ")
        require(world.supply_log == donor.supply_log, "Paired ordinary supply differs")
        run_id = f"{family}_{job['group_id']}_{arm}"
        save_world(world, output, batch_id, run_id, job["group_id"], family, arm, expected_hash,
                   analysis_config=world.config.analysis_config(), provenance=provenance, registry_binding=binding)
        run_ids.append(run_id)

    for arm, changes in E2.items():
        world = donor if arm == "I00" else ResearchWorld(replace(cfg, **changes), job["seed"]).run()
        save(world, "E2", arm)
    for arm, changes in job["branches"].items():
        world = ResearchWorld.from_snapshot(mother).fork(arm, changes).run()
        require(world.treatments[-1]["pre_treatment_state_hash"] == mother["state_hash"], "Fork state differs")
        if arm == "B0":
            require(world.trajectory == donor.trajectory and world.events == donor.events,
                    "B0 does not reproduce uninterrupted I00")
        save(world, "E4", arm, {"mother_snapshot_hash": mother["state_hash"], "fork_tick": job["fork_tick"]})
    for arm, changes in CLOSED.items():
        save(ResearchWorld(replace(cfg, **changes), job["seed"]).run(), "E3_closed", arm)
    diagnostics = {}
    for delay, world in make_replay_worlds(donor, (0, 1, 3, 10)).items():
        world.run()
        save(world, "E3_replay", f"delay{delay}", {"donor_run_id": f"E2_{job['group_id']}_I00",
             "replay_plan_hash": world.replay_plan.plan_hash})
        diagnostics[str(delay)] = replay_diagnostics(world)
    write_json(output / "diagnostics" / (job["group_id"] + ".json"), diagnostics)
    result = {"group_id": job["group_id"], "run_ids": run_ids,
              "checks": {"common_initial_state": True, "common_ordinary_supply": True,
                         "B0_uninterrupted_equivalence": True, "common_fork_state": True}}
    write_json(output / "groups" / (job["group_id"] + ".json"), result)
    return result


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
    output_name, job, manifest, registry = arguments
    binding = _authorize(registry, job, manifest["source_hash"])
    require(manifest.get("stage") == "formal" and manifest.get("formal_ready") is True
            and manifest.get("code_version") == RESEARCH_VERSION
            and manifest.get("registry_hash") == binding.registry_hash
            and manifest.get("specification_hash") == binding.specification_hash,
            "Formal manifest/registry binding mismatch")
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
        derived = validate_world_folder(folder, manifest["source_hash"], parents, registry_binding=binding)
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
                f"Unpaired or incomplete formal world: {name}")
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
