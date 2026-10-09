"""Read-only S1 artifact reconstruction; optionally compare two execution modes.

Usage: python -B scripts/validate_s1_outputs.py OUTPUT [--compare OTHER]
No physical simulation is rerun and no artifact is rewritten.
"""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

LATENT_FIELDS = {"P_true", "E_exposure", "P_trigger", "P_execution", "P_ref_packet",
                 "preferences", "truth_history", "initial_truth", "emotionality",
                 "baseline_trust", "citizens", "world", "evaluator"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError(f"Nonfinite JSON value: {value}")


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_object,
                      parse_constant=reject_constant)


def no_latent_fields(value, context):
    if isinstance(value, dict):
        forbidden = set(value) & LATENT_FIELDS
        require(not forbidden, f"Latent fields in {context}: {sorted(forbidden)}")
        for key, nested in value.items():
            no_latent_fields(nested, f"{context}.{key}")
    elif isinstance(value, list):
        for nested in value:
            no_latent_fields(nested, context)


def snapshot_state(snapshot, manifest, context):
    require(set(snapshot) == {"state", "state_hash"}, f"Invalid snapshot envelope: {context}")
    state = snapshot["state"]
    require(canonical_hash(state) == snapshot["state_hash"], f"Snapshot hash mismatch: {context}")
    require(state["source_hash"] == manifest["source_hash"] and
            state["code_version"] == manifest["code_version"], f"Snapshot source/version mismatch: {context}")
    require(state["schema"] == "research-1" and state["phase"] == "boundary_before_delivery",
            f"Snapshot schema/phase mismatch: {context}")
    require(type(state["tick"]) is int and 0 <= state["tick"] <= state["config"]["steps"],
            f"Invalid observed boundary: {context}")
    return state


def config_at(state, tick, snapshots):
    """Read ancestor configuration for a log prefix predating the latest fork."""
    seen = set()
    while state["snapshot_id"] is not None:
        treatment = state["logs"]["treatments"][-1]
        if tick >= treatment["at"]:
            break
        parent_hash = state["snapshot_id"]
        require(parent_hash not in seen and parent_hash in snapshots, "Missing/cyclic ancestor snapshot")
        seen.add(parent_hash)
        state = snapshots[parent_hash]["state"]
    return state["config"]


def validate_government(state, all_snapshots, context, replay=False):
    """Reconstruct beliefs and adaptive plans exclusively from permitted inputs."""
    from abm_jasss.government_sensing import GovernmentSensing, SensingSettings
    from abm_jasss.research_config import ResearchConfig
    from abm_jasss.research_governance import DecisionSettings, ResponseQueue
    from abm_jasss.research_randomness import AddressedRandomness
    from abm_jasss.research_replay import _information, PLAN_FIELDS
    from abm_jasss.research_world import jsonable

    logs, tick = state["logs"], state["tick"]
    trajectory, events = logs["trajectory"], logs["events"]
    for name in ("trajectory", "information_log", "government_estimates", "public_signal_ticks"):
        require(len(logs[name]) == tick, f"Incomplete observed prefix: {context}/{name}")
    require([row["step"] for row in trajectory] == list(range(tick)), f"Nonconsecutive ticks: {context}")
    require(len(state["packet_index"]) == tick, f"Generated packet count mismatch: {context}")
    packets = state["packet_index"]
    for packet_id, packet in packets.items():
        require(packet_id == packet["packet_id"] and 0 <= packet["generated_at"] < tick,
                f"Invalid generated packet: {context}")
    for packet in logs["observation_packets"]:
        value = {k: v for k, v in packet.items() if k != "received_at"}
        require(value == packets[packet["packet_id"]] and
                packet["available_at"] <= packet["received_at"] < tick,
                f"Invalid packet delivery: {context}")
    require({p["packet_id"] for p in state["pending_packets"]} ==
            {key for key, packet in packets.items() if packet["available_at"] >= tick},
            f"Pending packet lifecycle mismatch: {context}")
    for packet in state["pending_packets"]:
        require(packet == packets[packet["packet_id"]], f"Pending packet changed: {context}")

    settings = dict(state["sensing"]["settings"])
    for key in ("opaque_alpha", "opaque_rankings"):
        settings[key] = tuple(settings[key])
    initial = config_at(state, 0, all_snapshots)
    settings.update(pref_info=initial["pref_info"], rule_info=initial["rule_info"])
    sensing = GovernmentSensing(SensingSettings(**settings))
    queue, scheduled, execution = None, [], {}
    randomness = AddressedRandomness.from_snapshot(state["randomness"])
    for step, (info, estimate, row) in enumerate(zip(logs["information_log"], logs["government_estimates"], trajectory)):
        cfg = ResearchConfig.from_dict(config_at(state, step, all_snapshots))
        require(info["now"] == estimate["now"] == step, f"Government tick mismatch: {context}")
        no_latent_fields(info, f"{context}/information")
        no_latent_fields(estimate, f"{context}/estimate")
        if (sensing.settings.pref_info, sensing.settings.rule_info) != (cfg.pref_info, cfg.rule_info):
            saved = sensing.snapshot()
            saved["settings"].update(pref_info=cfg.pref_info, rule_info=cfg.rule_info)
            sensing = GovernmentSensing.from_snapshot(saved)
        # Constructors enforce exact whitelists and historical catalogue times;
        # update additionally enforces permissions and every evidence clock.
        reconstructed = jsonable(sensing.update(_information(info)))
        require(reconstructed == estimate, f"Government estimate reconstruction mismatch: {context}/{step}")
        survey = info["survey"]
        if survey is not None:
            require(any(all(record.get(key) == value for key, value in survey.items())
                        for record in logs["survey_log"] if record.get("status") == "valid"),
                    f"Unknown/modified delivered survey: {context}")
        packet = info["public_packet"]
        if packet is not None:
            require(packet == packets[packet["packet_id"]], f"Unknown/modified government packet: {context}")
            require(info["public_catalog"] == state["catalogs"][str(packet["window_end"])],
                    f"Historical catalogue mismatch: {context}")
        require(row["available_packet_id"] == (packet["packet_id"] if packet else None) and
                row["estimate_input_packet_id"] == estimate["estimate_input_packet_id"],
                f"Trajectory packet reference mismatch: {context}")
        require(row["P_hat_gov"] == estimate["estimate"] and row["has_data"] == estimate["has_data"],
                f"Trajectory estimate mismatch: {context}")
        require(row["P_true"] == state["truth_history"][str(step)], f"Truth history mismatch: {context}")
        if not replay:
            decision = DecisionSettings(cfg.n_topics, cfg.agenda_topics, cfg.response_threshold,
                cfg.response_strategy, cfg.response_wait_observations, cfg.response_capacity,
                cfg.government_delay, cfg.response_heat_retention, cfg.response_publish)
            if queue is None:
                queue = ResponseQueue(decision)
            queue.settings = decision
            if cfg.response_enabled and step % cfg.government_interval == 0:
                scheduled.extend(queue.schedule(step, sensing.estimate, sensing.has_data,
                    randomness.generator("response_decisions", step),
                    {"estimate_record": step, "information_hash": canonical_hash(info),
                     "latest_packet_id": None if packet is None else packet["packet_id"]}))
            for event in queue.due(step):
                execution[event["event_id"]] = step
    require(jsonable(sensing.snapshot()) == state["sensing"], f"Final sensing state mismatch: {context}")
    if not replay:
        require([{key: event[key] for key in PLAN_FIELDS} for event in events] == scheduled,
                f"Adaptive plans do not reconstruct from legal observations: {context}")
        require(queue is not None and jsonable(queue.snapshot()) == state["queue"],
                f"Adaptive queue reconstruction mismatch: {context}")
    require(len({event["event_id"] for event in events}) == len(events), f"Duplicate event identity: {context}")
    for event in events:
        executed, trigger, due = event["execution_step"], event["trigger_step"], event["due_step"]
        require(0 <= trigger < tick and due >= trigger and
                (executed == due < tick if executed is not None else due >= tick),
                f"Invalid event timing: {context}")
        require(event["P_trigger"] == trajectory[trigger]["P_true"] and
                event["P_execution"] == (None if executed is None else trajectory[executed]["P_true"]),
                f"Event truth clock mismatch: {context}")
        if not replay:
            require(executed == execution.get(event["event_id"]), f"Adaptive execution mismatch: {context}")
    for row in trajectory:
        step = row["step"]
        expected = (sum(e["trigger_step"] == step for e in events),
                    sum(e["execution_step"] == step for e in events),
                    sum(e["trigger_step"] <= step < e["due_step"] for e in events))
        require((row["responses_scheduled"], row["responses_executed"], row["pending_count"]) == expected,
                f"Response accounting mismatch: {context}")


def validate(output):
    output = Path(output).resolve(strict=True)
    require(output.is_dir(), "Output must be a directory")
    paths = list(output.rglob("*"))
    require(not any(path.is_symlink() for path in paths), "Symlinks are not permitted in an artifact bundle")
    actual = {path.relative_to(output).as_posix(): path for path in paths if path.is_file()}
    hashes = read(output / "artifact_hashes.json")
    require(set(hashes) == set(actual) - {"artifact_hashes.json"}, "Artifact file inventory mismatch")
    for relative, digest in hashes.items():
        require(sha256(actual[relative]) == digest, f"Artifact hash mismatch: {relative}")
    manifest = read(output / "manifest.json")
    require(manifest["stage"] == "S1" and manifest["formal_ready"] is False and
            manifest["status"] == "complete" and manifest["failed_groups"] == 0,
            "Only completed development S1 batches can be validated")
    require(manifest["schema_version"] == "s1-artifacts-1", "Unknown S1 artifact schema")
    spec = read(output / "configuration.json")
    require(spec == manifest["specification"] and canonical_hash(spec) == manifest["specification_hash"],
            "Specification/manifest mismatch")
    launch = read(output / "launch_manifest.json")
    require(launch["status"] == "running" and all(launch[key] == manifest[key] for key in launch if key != "status"),
            "Launch/final manifest mismatch")
    archived = {p.name: sha256(p) for p in sorted((output / "source_snapshot" / "abm_jasss").glob("*.py"))}
    require(archived == manifest["source_sha256"] and canonical_hash(archived) == manifest["source_hash"],
            "Archived source/manifest mismatch")
    # Replay plans bind the entire engine source; reject a different live engine
    # instead of silently rebuilding a historical batch using new equations.
    require({p.name: sha256(p) for p in sorted((ROOT / "abm_jasss").glob("*.py"))} == archived,
            "Live analysis source differs from the archived S1 engine")

    from abm_jasss.research_config import ResearchConfig
    from abm_jasss.research_dynamics import rebuild_dynamics_diagnostics
    from abm_jasss.research_replay import PLAN_FIELDS, REPLAY_SCHEMA, _ReplayQueue, rebuild_replay_diagnostics
    from abm_jasss.research_s1_cli import LOG_FILES, aggregate, build_derived, resolve_design
    from abm_jasss.research_world import jsonable

    jobs = read(output / "resolved_design.json")
    require(jobs == resolve_design(spec), "Resolved S1 design mismatch")
    require(manifest["expected_groups"] == manifest["completed_groups"] == len(jobs), "Group accounting mismatch")
    validation = read(output / "validation.json")
    require(validation["stage"] == "S1" and validation["formal_ready"] is False and
            validation["status"] == "passed", "Invalid stored validation status")
    recorded_groups = {group["group_id"]: group for group in validation["groups"]}
    require(len(recorded_groups) == len(jobs) and set(recorded_groups) == {job["group_id"] for job in jobs},
            "Validation group inventory mismatch")

    snapshots, raw, metadata, derived = {}, {}, {}, {}
    for folder in sorted((output / "raw").iterdir()):
        require(folder.is_dir(), "Unexpected raw artifact entry")
        name = folder.name
        snapshot = read(folder / "evaluator" / "snapshot.json")
        snapshot_state(snapshot, manifest, name)
        snapshots[snapshot["state_hash"]] = snapshot
        raw[name], metadata[name] = snapshot, read(folder / "metadata.json")
    dynamic_snapshots = {}
    for job in jobs:
        if job["kind"] == "dynamics":
            saved = {path.stem: read(path) for path in sorted((output / "dynamic_snapshots" / job["group_id"]).glob("*.json"))}
            for name, snapshot in saved.items():
                snapshot_state(snapshot, manifest, f"{job['group_id']}/{name}")
                snapshots[snapshot["state_hash"]] = snapshot
            dynamic_snapshots[job["group_id"]] = saved
    checkpoints, trajectory_count, event_count = 0, 0, 0
    for name, snapshot in raw.items():
        state, meta = snapshot["state"], metadata[name]
        cfg = ResearchConfig.from_dict(state["config"])
        require(meta["run_id"] == name and meta["world_id"] == f"{manifest['batch_id']}/{name}" and
                meta["batch_id"] == manifest["batch_id"] and meta["engine_world_id"] == state["world_id"] and
                meta["group_id"] in recorded_groups and
                name == f"{meta['scenario']}_{meta['group_id']}_{meta['condition']}",
                f"World identity mismatch: {name}")
        require(meta["source_hash"] == manifest["source_hash"] and meta["code_version"] == manifest["code_version"]
                and meta["stage"] == "S1" and meta["formal_ready"] is False and meta["failure"] is None
                and meta["retry"] == 0, f"World provenance/status mismatch: {name}")
        require(meta["schema_version"] == manifest["schema_version"] and meta["engine_schema"] == state["schema"],
                f"World schema mismatch: {name}")
        require(meta["config"] == state["config"] and meta["config_hash"] == canonical_hash(state["config"])
                and meta["analysis_config"] == jsonable(cfg.analysis_config()), f"World configuration mismatch: {name}")
        require(meta["status"] == ("complete" if state["tick"] == cfg.steps else "checkpoint"),
                f"World completion status mismatch: {name}")
        checkpoints += meta["status"] == "checkpoint"
        require(meta["final_snapshot_hash"] == snapshot["state_hash"] and
                meta["parent_snapshot_hash"] == state["snapshot_id"] and
                meta["parent_engine_world_id"] == state["parent_world_id"] and
                meta["engine_reference_id"] == f"{manifest['batch_id']}/engine/{state['world_id']}" and
                meta["parent_world_id"] == (None if state["parent_world_id"] is None else
                    f"{manifest['batch_id']}/engine/{state['parent_world_id']}"), f"Parent/snapshot reference mismatch: {name}")
        require(meta["seed"] == state["seed"] and meta["initial_condition_id"] == state["initial_condition"] and
                meta["initial_state_hash"] == state["initial_state_hash"] and
                meta["randomness"] == state["randomness"] and
                meta["shock_tape_hash"] == canonical_hash(state["randomness"]) and
                meta["shock_tape_id"] == f"{state['randomness']['schema']}/seed{state['seed']}" and
                meta["shock_tape_kind"] == "addressed_randomness_not_pregenerated_tape" and
                meta["ordinary_supply_hash"] == canonical_hash(state["logs"]["supply_log"]),
                f"Initial condition/randomness/supply mismatch: {name}")
        require(meta["fork_phase"] == state["phase"] and meta["treatments"] == state["logs"]["treatments"],
                f"Treatment metadata mismatch: {name}")
        require(meta["information_condition"] == {"PrefInfo": cfg.pref_info, "RuleInfo": cfg.rule_info}
                and meta["taxonomy_version"] == f"synthetic-topics-{cfg.n_topics}-v1"
                and meta["time_unit"] == "simulation_tick" and meta["signal_schema"] == "public-signals-1"
                and meta["outcome_schema"] == "research-outcomes-1", f"Information/taxonomy schema mismatch: {name}")
        for field, relative in LOG_FILES.items():
            require(read(output / "raw" / name / relative) == state["logs"][field], f"Snapshot/log mismatch: {name}/{field}")
        actions = read(output / "raw" / name / "government" / "actions.json")
        require(actions == [{key: value for key, value in event.items() if key not in {"P_trigger", "P_execution"}}
                            for event in state["logs"]["events"]], f"Government action split mismatch: {name}")
        for field, value in (("actions", actions), ("public_signal_ticks", state["logs"]["public_signal_ticks"]),
                             ("packets", state["packet_index"])):
            no_latent_fields(value, f"{name}/{field}")
        replay = state["queue"].get("queue_mode") == REPLAY_SCHEMA
        require(replay == (meta["scenario"] == "replay"), f"Replay scenario mismatch: {name}")
        validate_government(state, snapshots, name, replay)
        rebuilt = jsonable(build_derived(state, meta))
        require(rebuilt == read(output / "derived" / f"{name}.json"), f"Derived reconstruction mismatch: {name}")
        derived[name] = rebuilt
        trajectory_count += state["tick"]
        event_count += len(state["logs"]["events"])
    require(manifest["world_records"] == len(raw) and
            {p.stem for p in (output / "derived").glob("*.json")} == set(raw), "World/derived inventory mismatch")

    groups = []
    for job in jobs:
        group_id = job["group_id"]
        names = {name for name, meta in metadata.items() if meta["group_id"] == group_id}
        recorded = recorded_groups[group_id]
        require(set(recorded["run_ids"]) == names and len(recorded["run_ids"]) == len(names)
                and recorded["kind"] == job["kind"], f"Group run inventory mismatch: {group_id}")
        checks = read(output / "checks" / f"{group_id}.json")
        require(checks == recorded["checks"] and all(value is True for value in checks.values()),
                f"Stored group checks mismatch: {group_id}")
        if job["kind"] == "mechanisms":
            expected_names = {f"closed_{group_id}_{condition}" for condition in job["conditions"]} | {
                f"replay_{group_id}_delay{delay}" for delay in job["delays"]}
            require(names == expected_names, f"Mechanism condition inventory mismatch: {group_id}")
            donor_name = f"closed_{group_id}_baseline"
            donor = raw[donor_name]["state"]
            base = ResearchConfig.from_dict(job["model"])
            replay_checks = {}
            for name in sorted(names):
                state, meta = raw[name]["state"], metadata[name]
                require(state["seed"] == job["seed"] and state["tick"] == base.steps and
                        state["initial_state_hash"] == donor["initial_state_hash"] and
                        state["logs"]["supply_log"] == donor["logs"]["supply_log"], f"Unpaired mechanism world: {name}")
                if meta["scenario"] == "closed":
                    require(meta["condition"] in job["conditions"] and state["config"] ==
                            jsonable(replace(base, **job["conditions"][meta["condition"]]).to_dict()),
                            f"Closed condition configuration mismatch: {name}")
                    require(not state["logs"]["treatments"] and state["parent_world_id"] is None,
                            f"Unexpected closed-world treatment: {name}")
                else:
                    queue, plan = state["queue"], state["queue"]["plan"]
                    delay = queue["administrative_delay"]
                    require(meta["condition"] == f"delay{delay}" and delay in job["delays"] and
                            state["config"] == jsonable(replace(base, government_delay=delay).to_dict()),
                            f"Replay configuration mismatch: {name}")
                    require(plan["donor_world_id"] == donor["world_id"] and plan["donor_seed"] == donor["seed"] and
                            plan["donor_config"] == donor["config"] and plan["donor_source_hash"] == manifest["source_hash"]
                            and plan["donor_snapshot_hash"] == raw[donor_name]["state_hash"] and
                            plan["donor_information_hash"] == canonical_hash(donor["logs"]["information_log"])
                            and plan["events"] == [{key: event[key] for key in PLAN_FIELDS} for event in donor["logs"]["events"]],
                            f"Replay donor reference mismatch: {name}")
                    require(queue["plan_hash"] == canonical_hash(plan) and meta["provenance"] == {
                        "donor_run_id": donor_name, "replay_plan_hash": queue["plan_hash"]}, f"Replay plan metadata mismatch: {name}")
                    _ReplayQueue.from_snapshot(queue)
                    require(queue["last_step"] == state["tick"] - 1, f"Replay cursor/boundary mismatch: {name}")
                    replay_checks[str(delay)] = rebuild_replay_diagnostics(state["logs"]["trajectory"],
                        state["logs"]["events"], plan, delay, base.steps)
            require(replay_checks == read(output / "diagnostics" / f"{group_id}.json"),
                    f"Replay diagnostic reconstruction mismatch: {group_id}")
        else:
            world_snapshots = {metadata[name]["condition"]: raw[name] for name in names}
            require(len(world_snapshots) == len(names) and all(metadata[name]["scenario"] == "dynamic" for name in names),
                    f"Dynamic world condition mismatch: {group_id}")
            rebuilt = rebuild_dynamics_diagnostics(ResearchConfig.from_dict(job["model"]), job["seed"], job["spec"],
                                                    world_snapshots, dynamic_snapshots[group_id])
            require(jsonable(rebuilt) == read(output / "diagnostics" / f"{group_id}.json"),
                    f"Dynamic diagnostic reconstruction mismatch: {group_id}")
        groups.append({"group_id": group_id, "kind": job["kind"], "alpha": job.get("alpha"),
                       "records": [derived[name] for name in sorted(names)], "checks": checks})
    groups.sort(key=lambda group: group["group_id"])
    require(jsonable(aggregate(groups)) == read(output / "paired_diagnostics.json"), "Paired diagnostic reconstruction mismatch")
    require({p.name: sha256(p) for p in sorted((ROOT / "abm_jasss").glob("*.py"))} == archived,
            "Analysis source changed during validation")
    return {"status": "passed", "stage": "S1", "formal_ready": False, "read_only": True,
            "batch_id": manifest["batch_id"], "hashed_files": len(hashes), "groups": len(jobs),
            "world_records": len(raw), "checkpoint_records": checkpoints,
            "trajectory_records": trajectory_count, "response_events": event_count,
            "derived_rebuilt": True, "replay_diagnostics_rebuilt": True, "dynamic_diagnostics_rebuilt": True,
            "paired_diagnostics_rebuilt": True,
            "scope": "Stored artifact integrity, legal decision reconstruction and descriptive statistics; no formal release"}


def normalized_artifact(relative, value, batch_id):
    """Normalize only known execution-envelope identifiers, never model fields."""
    if relative in {"manifest.json", "launch_manifest.json"}:
        return {key: nested for key, nested in value.items()
                if key not in {"batch_id", "started_at", "finished_at", "workers"}}
    if relative.startswith("raw/") and relative.endswith("/metadata.json"):
        result = dict(value)
        result.pop("batch_id")
        for key in ("world_id", "parent_world_id", "engine_reference_id"):
            if result[key] is not None:
                require(result[key].startswith(batch_id + "/"), f"Unknown global identifier: {relative}/{key}")
                result[key] = result[key][len(batch_id) + 1:]
        return result
    return value


def compare(output, other):
    first, second = validate(output), validate(other)
    output, other = Path(output), Path(other)
    left, right = read(output / "artifact_hashes.json"), read(other / "artifact_hashes.json")
    require(set(left) == set(right), "Compared artifact inventories differ")
    for relative in sorted(left):
        if relative.endswith(".json"):
            a = normalized_artifact(relative, read(output / relative), first["batch_id"])
            b = normalized_artifact(relative, read(other / relative), second["batch_id"])
            require(a == b, f"Serial/parallel semantic mismatch: {relative}")
        else:
            require(left[relative] == right[relative], f"Serial/parallel file mismatch: {relative}")
    return {"status": "passed", "read_only": True, "formal_ready": False, "stage": "S1",
            "comparison": "equal after known batch IDs, timestamps and worker-count normalization",
            "compared_files": len(left), "first": first, "second": second}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    try:
        result = compare(args.output, args.compare) if args.compare else validate(args.output)
    except (ValueError, TypeError, KeyError, IndexError, OSError) as error:
        print(json.dumps({"status": "failed", "read_only": True, "error": str(error)}, ensure_ascii=False))
        raise SystemExit(1)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
