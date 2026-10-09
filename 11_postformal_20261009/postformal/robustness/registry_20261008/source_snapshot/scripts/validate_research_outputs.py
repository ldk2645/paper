"""Read-only integrity and semantic validation of a completed research S0 batch.

Usage: python -B scripts/validate_research_outputs.py OUTPUT
No simulation is rerun and no file is created or rewritten. Rebuilding derived
statistics uses the live research_outcomes module only after its file hash is
verified against the batch's stored source; other live model files may differ.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CELLS = {"I00": (False, False), "I10": (True, False),
         "I01": (False, True), "I11": (True, True)}
BRANCHES = {"B0", "B1", "B2", "B3", "B4"}
METRICS = ("platform_representation_gap", "perception_error",
           "targeting_error_trigger", "targeting_error_execution", "exposure_gap", "waiting_time",
           "response_completion_L", "execution_coverage")
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
    return json.loads(path.read_text(encoding="utf-8-sig"),
                      object_pairs_hook=unique_object, parse_constant=reject_constant)


def no_latent_fields(value, context):
    if isinstance(value, dict):
        forbidden = set(value) & LATENT_FIELDS
        require(not forbidden, f"Latent fields in {context}: {sorted(forbidden)}")
        for key, nested in value.items():
            no_latent_fields(nested, f"{context}.{key}")
    elif isinstance(value, list):
        for nested in value:
            no_latent_fields(nested, context)


def validate_snapshot(snapshot, manifest, context):
    require(set(snapshot) == {"state", "state_hash"}, f"Invalid snapshot envelope: {context}")
    state = snapshot["state"]
    require(canonical_hash(state) == snapshot["state_hash"], f"Snapshot hash mismatch: {context}")
    require(state["source_hash"] == manifest["source_hash"], f"Snapshot source mismatch: {context}")
    require(state["schema"] == manifest["schema_version"], f"Snapshot schema mismatch: {context}")
    require(state["code_version"] == manifest["code_version"], f"Snapshot version mismatch: {context}")
    require(state["phase"] == "boundary_before_delivery", f"Invalid snapshot phase: {context}")
    return state


def validate(output):
    output = Path(output).resolve(strict=True)
    require(output.is_dir(), "Output must be a directory")
    paths = list(output.rglob("*"))
    require(not any(path.is_symlink() for path in paths), "Symlinks are not supported in an artifact bundle")
    actual = {path.relative_to(output).as_posix(): path for path in paths if path.is_file()}
    require("artifact_hashes.json" in actual, "Missing artifact_hashes.json")
    hashes = read(output / "artifact_hashes.json")
    expected_files = set(actual) - {"artifact_hashes.json"}
    require(set(hashes) == expected_files,
            f"Artifact file set mismatch; missing={sorted(set(hashes) - expected_files)}, "
            f"unlisted={sorted(expected_files - set(hashes))}")
    for relative, digest in hashes.items():
        require(sha256(actual[relative]) == digest, f"Artifact SHA256 mismatch: {relative}")

    manifest = read(output / "manifest.json")
    launch = read(output / "launch_manifest.json")
    require(manifest["status"] == "complete", "Batch is not complete")
    require(manifest["stage"] == "S0" and manifest["formal_ready"] is False,
            "Only S0 development outputs with formal_ready=false are supported")
    require(manifest["failed_groups"] == 0 and "failures.json" not in actual, "Batch contains failures")
    require(launch["status"] == "running", "Invalid launch status")
    for key in ("batch_id", "stage", "formal_ready", "code_version", "schema_version", "source_hash",
                "specification", "specification_hash", "expected_groups", "expected_world_records"):
        require(launch[key] == manifest[key], f"Launch/final manifest disagreement: {key}")
    specification = read(output / "configuration.json")
    require(specification == manifest["specification"], "Configuration differs from manifest")
    require(canonical_hash(specification) == manifest["specification_hash"], "Specification hash mismatch")
    require(specification["stage"] == "S0" and specification["formal_ready"] is False,
            "Specification is not S0 development")

    source_dir = output / "source_snapshot" / "abm_jasss"
    stored_sources = {path.name: sha256(path) for path in source_dir.glob("*.py")}
    require(stored_sources == manifest["source_sha256"], "Stored source file set/hash mismatch")
    require(canonical_hash(stored_sources) == manifest["source_hash"], "Stored combined source hash mismatch")
    analyzer_hash = sha256(ROOT / "abm_jasss" / "research_outcomes.py")
    require(analyzer_hash == stored_sources.get("research_outcomes.py"),
            "Live research_outcomes.py differs from stored version; use the matching analysis version")
    # Import only after its bytes are known to match the stored analyzer.
    from abm_jasss.research_outcomes import paired_contrast, summarize_world

    jobs = read(output / "resolved_design.json")
    expected_groups = {f"a{index:02d}_seed{seed}": (alpha, seed)
                       for index, alpha in enumerate(specification["alphas"])
                       for seed in specification["seeds"]}
    require(len(jobs) == len(expected_groups), "Resolved job count mismatch")
    require({job["group_id"] for job in jobs} == set(expected_groups), "Resolved group identities mismatch")
    require(set(specification["branches"]) == BRANCHES, "S0 must contain B0-B4")
    count = len(jobs)
    for key in ("expected_groups", "completed_groups"):
        require(manifest[key] == count, f"Manifest {key} mismatch")
    for key in ("expected_world_records", "world_records"):
        require(manifest[key] == 9 * count, f"Manifest {key} mismatch")
    expected_runs = {f"{scenario}_{job['group_id']}_{condition}"
                     for job in jobs for scenario, conditions in (("E2", CELLS), ("E4", BRANCHES))
                     for condition in conditions}
    require({p.name for p in (output / "raw").iterdir() if p.is_dir()} == expected_runs,
            "Raw world directory set mismatch")
    require({p.name for p in (output / "derived").iterdir()} == {f"{run}.json" for run in expected_runs},
            "Derived world file set mismatch")
    for directory in ("snapshots", "checks"):
        require({p.name for p in (output / directory).iterdir()} == {f"{g}.json" for g in expected_groups},
                f"{directory} group file set mismatch")

    validation = read(output / "validation.json")
    require(validation["status"] == "passed" and validation["formal_ready"] is False
            and validation["stage"] == "S0", "Invalid S0 validation status")
    require((validation["groups"], validation["e2_worlds"], validation["e4_suffixes"])
            == (count, 4 * count, 5 * count), "Validation counts mismatch")
    require(set(validation["checks"]) == set(expected_groups), "Validation check groups mismatch")

    results, group_records, initial_by_seed = {}, {}, {}
    event_count = pending_count = trajectory_count = 0
    for job in jobs:
        group = job["group_id"]
        alpha, seed = expected_groups[group]
        require((job["alpha"], job["seed"]) == (alpha, seed), f"Resolved alpha/seed mismatch: {group}")
        require(job["fork_tick"] == specification["fork_tick"] and
                job["branches"] == specification["branches"], f"Resolved treatment mismatch: {group}")
        for key, value in specification["model"].items():
            require(job["model"][key] == (alpha if key == "alpha" else value),
                    f"Resolved model mismatch: {group}/{key}")
        require(job["model"]["alpha"] == alpha, f"Resolved ranking mismatch: {group}")
        checks = read(output / "checks" / f"{group}.json")
        require(checks and all(value is True for value in checks.values()), f"Failed group checks: {group}")
        require(checks == validation["checks"][group], f"Group validation mismatch: {group}")
        mother_snapshot = read(output / "snapshots" / f"{group}.json")
        mother = validate_snapshot(mother_snapshot, manifest, group)
        require(mother["tick"] == job["fork_tick"] and mother["seed"] == seed,
                f"Mother snapshot boundary/seed mismatch: {group}")
        require(mother["config"] == job["model"], f"Mother configuration mismatch: {group}")
        initial_hash = mother["initial_state_hash"]
        if seed in initial_by_seed:
            require(initial_by_seed[seed] == initial_hash, f"Initial physical states differ across alpha: {seed}")
        initial_by_seed[seed] = initial_hash
        records = {}
        for scenario, conditions in (("E2", CELLS), ("E4", sorted(BRANCHES))):
            for condition in conditions:
                run_id = f"{scenario}_{group}_{condition}"
                folder = output / "raw" / run_id
                metadata = read(folder / "metadata.json")
                config = dict(job["model"])
                if scenario == "E2":
                    config.update(zip(("pref_info", "rule_info"), CELLS[condition]))
                else:
                    config.update(job["branches"][condition])
                require(metadata["config"] == config, f"Unexpected world configuration: {run_id}")
                require(metadata["config_hash"] == canonical_hash(config), f"Config hash mismatch: {run_id}")
                require(metadata["source_hash"] == manifest["source_hash"] and
                        metadata["code_version"] == manifest["code_version"], f"World source mismatch: {run_id}")
                require(metadata["formal_ready"] is False and metadata["status"] == "complete",
                        f"Invalid world status: {run_id}")
                require((metadata["batch_id"], metadata["run_id"], metadata["group_id"],
                         metadata["scenario"], metadata["condition"], metadata["seed"])
                        == (manifest["batch_id"], run_id, group, scenario, condition, seed),
                        f"World identity mismatch: {run_id}")
                require(metadata["world_id"] == f"{manifest['batch_id']}/{run_id}", f"World ID mismatch: {run_id}")
                require(metadata["initial_state_hash"] == initial_hash, f"Initial state reference mismatch: {run_id}")
                analysis = dict(config)
                if scenario == "E4":
                    analysis["completion_start"] = max(config["completion_start"], job["fork_tick"])
                if analysis["completion_end"] is None:
                    analysis["completion_end"] = max(analysis["completion_start"],
                        config["steps"] - config["completion_followup"] - 1)
                require(metadata["analysis_config"] == analysis, f"Analysis configuration mismatch: {run_id}")
                snapshot = read(folder / "snapshot_final.json")
                state = validate_snapshot(snapshot, manifest, run_id)
                require(state["tick"] == config["steps"] and state["config"] == config,
                        f"Final snapshot horizon/config mismatch: {run_id}")
                require(state["initial_state_hash"] == initial_hash and state["seed"] == seed,
                        f"Final snapshot initial state mismatch: {run_id}")
                require(state["world_id"] == metadata["engine_world_id"], f"Engine identity mismatch: {run_id}")
                require(state["randomness"] == metadata["randomness"] and
                        canonical_hash(state["randomness"]) == metadata["shock_address_hash"],
                        f"Randomness manifest mismatch: {run_id}")
                require(state["randomness"]["seed"] == seed, f"Randomness seed mismatch: {run_id}")
                logs = state["logs"]
                file_logs = {"trajectory": "evaluator/trajectory.json", "events": "evaluator/response_events.json",
                             "public_signal_ticks": "public_signal_ticks.json", "information_log": "government/information.json",
                             "government_estimates": "government/estimates.json", "supply_log": "supply.json",
                             "publication_log": "publications.json", "survey_log": "surveys.json"}
                for key, relative in file_logs.items():
                    require(read(folder / relative) == logs[key], f"Snapshot/log mismatch: {run_id}/{relative}")
                trajectory, events = logs["trajectory"], logs["events"]
                infos, estimates = logs["information_log"], logs["government_estimates"]
                require([r["step"] for r in trajectory] == list(range(config["steps"])), f"Incomplete trajectory: {run_id}")
                require(len(infos) == len(estimates) == len(logs["public_signal_ticks"]) == config["steps"],
                        f"Incomplete tick logs: {run_id}")
                packets = read(folder / "observation_packets.json")
                require(packets["received"] == logs["observation_packets"] and
                        packets["pending"] == state["pending_packets"], f"Packet lifecycle mismatch: {run_id}")
                generated = {p["packet_id"]: p for p in packets["generated"]}
                require(len(generated) == len(packets["generated"]) == config["steps"] and
                        generated == state["packet_index"], f"Generated packet index mismatch: {run_id}")
                for delivered in packets["received"]:
                    packet = {k: v for k, v in delivered.items() if k != "received_at"}
                    require(packet == generated[packet["packet_id"]] and
                            packet["available_at"] <= delivered["received_at"] < config["steps"],
                            f"Invalid packet delivery: {run_id}")
                for info, estimate, row in zip(infos, estimates, trajectory):
                    tick = row["step"]
                    require(info["now"] == estimate["now"] == tick, f"Government tick mismatch: {run_id}")
                    packet = info["public_packet"]
                    if packet is not None:
                        require(packet == generated[packet["packet_id"]] and
                                packet["available_at"] <= tick and packet["window_end"] < tick,
                                f"Future/unknown government packet: {run_id}")
                    pref = config["pref_info"] if scenario == "E2" or tick >= job["fork_tick"] else False
                    require(pref or info["survey"] is None, f"Unauthorized survey: {run_id}")
                    require(config["rule_info"] or info["rule"] is None, f"Unauthorized rule: {run_id}")
                    for kind in ("survey", "rule"):
                        if info[kind] is not None:
                            require(info[kind]["available_at"] <= tick, f"Future auxiliary information: {run_id}")
                    require(row["available_packet_id"] == (packet["packet_id"] if packet else None),
                            f"Available packet reference mismatch: {run_id}")
                    used = estimate["estimate_input_packet_id"]
                    require(row["estimate_input_packet_id"] == used, f"Used packet reference mismatch: {run_id}")
                    if used is not None:
                        require(generated[used]["available_at"] <= estimate["estimate_updated_at"] <= tick,
                                f"Estimate used unavailable packet: {run_id}")
                actions = read(folder / "government" / "actions.json")
                require(actions == [{k: v for k, v in e.items() if k not in {"P_trigger", "P_execution"}}
                                    for e in events], f"Government/evaluator action mismatch: {run_id}")
                for name, value in (("information", infos), ("estimates", estimates), ("actions", actions),
                                    ("public_signal_ticks", logs["public_signal_ticks"]), ("packets", packets)):
                    no_latent_fields(value, f"{run_id}/{name}")
                pending = state["queue"]["pending"]
                pending_ids = {p["event_id"] for p in pending}
                require(len(pending_ids) == len(pending) and
                        pending_ids == {e["event_id"] for e in events if e["execution_step"] is None},
                        f"Pending queue/event mismatch: {run_id}")
                for event in events:
                    executed = event["execution_step"]
                    require(executed == event["due_step"] if executed is not None else event["due_step"] >= config["steps"],
                            f"Invalid execution/due time: {run_id}")
                    ref = event["information_ref"]
                    require(ref["estimate_record"] == event["trigger_step"] and
                            canonical_hash(infos[ref["estimate_record"]]) == ref["information_hash"],
                            f"Action information reference mismatch: {run_id}")
                require(canonical_hash(logs["supply_log"]) == metadata["ordinary_supply_hash"],
                        f"Ordinary supply hash mismatch: {run_id}")
                derived = read(output / "derived" / f"{run_id}.json")
                rebuilt = summarize_world(trajectory, events, metadata["analysis_config"])
                require(derived == {"run_id": run_id, "group_id": group, "scenario": scenario,
                                    "condition": condition, "summary": rebuilt}, f"Derived summary mismatch: {run_id}")
                require(rebuilt["pending_count"] == len(pending) and rebuilt["scheduled_count_total"] == len(events),
                        f"Summary event accounting mismatch: {run_id}")
                if scenario == "E4":
                    require(metadata["snapshot_id"] == state["snapshot_id"] == mother_snapshot["state_hash"],
                            f"Branch mother snapshot reference mismatch: {run_id}")
                    require(metadata["parent_world_id"] == f"{manifest['batch_id']}/E2_{group}_I00" and
                            state["parent_world_id"] == mother["world_id"], f"Branch parent reference mismatch: {run_id}")
                    require(metadata["fork_tick"] == job["fork_tick"] and
                            metadata["fork_phase"] == mother["phase"], f"Branch fork boundary mismatch: {run_id}")
                    require(metadata["treatments"] == logs["treatments"] and len(logs["treatments"]) == 1,
                            f"Treatment record mismatch: {run_id}")
                    treatment = logs["treatments"][0]
                    require(treatment["changes"] == job["branches"][condition] and
                            treatment["pre_treatment_state_hash"] == mother_snapshot["state_hash"],
                            f"Treatment specification mismatch: {run_id}")
                    inherited = {str(p["topic"]): p for p in mother["queue"]["pending"]}
                    require(canonical_hash(inherited) == treatment["inherited_queue_hash"],
                            f"Inherited queue hash mismatch: {run_id}")
                    event_index = {e["event_id"]: e for e in events}
                    for plan in inherited.values():
                        require(all(event_index[plan["event_id"]][k] == v for k, v in plan.items()),
                                f"Inherited action was rewritten: {run_id}")
                else:
                    require(metadata["snapshot_id"] is None and metadata["parent_world_id"] is None and
                            not logs["treatments"], f"Unexpected E2 parent/treatment: {run_id}")
                results[run_id] = derived
                records[f"{scenario}_{condition}"] = state
                event_count += len(events)
                pending_count += len(pending)
                trajectory_count += len(trajectory)
        baseline = records["E2_I00"]["logs"]
        for name, state in records.items():
            require(state["logs"]["supply_log"] == baseline["supply_log"], f"Unpaired ordinary supply: {group}/{name}")
            routine = [item for item in state["logs"]["publication_log"] if item["source"] == 1]
            require(routine == [item for item in baseline["publication_log"] if item["source"] == 1],
                    f"Unpaired routine publications: {group}/{name}")
        for key, value in baseline.items():
            if key != "treatments":
                require(records["E4_B0"]["logs"][key] == value, f"B0 continuation mismatch: {group}/{key}")
        group_records[group] = records

    rebuilt_pairs = {}
    for alpha in sorted({job["alpha"] for job in jobs}):
        selected_jobs = [job for job in jobs if job["alpha"] == alpha]
        strata = {}
        for scenario in ("E2", "E4"):
            strata[scenario] = {}
            for metric in METRICS:
                values = {job["group_id"]: {result["condition"]: result["summary"][metric]
                          for result in results.values() if result["group_id"] == job["group_id"]
                          and result["scenario"] == scenario} for job in selected_jobs}
                contrasts = paired_contrast(values) if scenario == "E2" else {
                    branch: paired_contrast(values, {branch: 1, "B0": -1}) for branch in ("B1", "B2", "B3", "B4")}
                for result in contrasts.values():
                    for key in ("normal95_interval", "standard_error", "interval_method"):
                        result.pop(key, None)
                    result["scope"] = "S0 descriptive pairing and missingness only; no inferential claim"
                strata[scenario][metric] = contrasts
        rebuilt_pairs[str(alpha)] = strata
    require(rebuilt_pairs == read(output / "paired_diagnostics.json"), "Paired diagnostics rebuild mismatch")
    require(analyzer_hash == sha256(ROOT / "abm_jasss" / "research_outcomes.py"), "Analyzer changed during validation")
    return {"status": "passed", "stage": "S0", "formal_ready": False, "read_only": True,
            "batch_id": manifest["batch_id"], "hashed_files": len(hashes), "groups": count,
            "e2_worlds": 4 * count, "e4_suffixes": 5 * count, "rebuilt_world_summaries": len(results),
            "trajectory_records": trajectory_count, "response_events": event_count,
            "pending_events": pending_count, "paired_diagnostics_rebuilt": True,
            "analysis_source_sha256": analyzer_hash,
            "initial_state_validation": "stored initial hashes agree across paired worlds and snapshot references",
            "scope": "Stored artifact integrity and recorded semantics; no fresh simulation or formal release"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        result = validate(args.output)
    except (ValueError, TypeError, KeyError, IndexError, OSError) as exc:
        print(json.dumps({"status": "failed", "read_only": True, "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
