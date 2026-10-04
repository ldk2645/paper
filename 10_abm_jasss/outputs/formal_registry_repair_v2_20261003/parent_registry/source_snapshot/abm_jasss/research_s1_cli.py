"""S1 development: mechanism controls, controlled replay and dynamic diagnostics."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import shutil
import sys
import traceback
import uuid

import numpy as np

from .research_cli import file_hash, require, write_json
from .research_config import ResearchConfig, RESEARCH_VERSION, SCHEMA_VERSION
from .research_outcomes import summarize_world, paired_contrast
from .research_world import ResearchWorld, canonical_hash, jsonable, source_hash

ROOT = Path(__file__).resolve().parents[1]
METRICS = ("platform_representation_gap", "perception_error", "targeting_error_trigger",
           "targeting_error_execution", "exposure_gap", "waiting_time", "response_completion_L",
           "execution_coverage")
LOG_FILES = {"trajectory": "evaluator/trajectory.json", "events": "evaluator/response_events.json",
             "information_log": "government/information.json", "government_estimates": "government/estimates.json",
             "public_signal_ticks": "public_signal_ticks.json", "observation_packets": "received_packets.json",
             "supply_log": "supply.json", "publication_log": "publications.json", "survey_log": "surveys.json"}


def closed_conditions(config, spec):
    result = {}
    for delay in spec["administrative_delays"]:
        for observation in spec["observation_delays"]:
            result[f"delay{delay}_obs{observation}"] = {"government_delay": delay, "observation_delay": observation}
    for capacity in spec["scheduling_capacities"]:
        result[f"capacity{capacity}"] = {"response_capacity": capacity}
    result.update(heat_off={"full_heat_off": True}, alpha_zero={"alpha": 0.},
                  heat_control_off={"response_heat_retention": 1.}, reply_off={"response_publish": False},
                  softmax={"ranking": "softmax"}, softmax_heat_off={"ranking": "softmax", "full_heat_off": True},
                  trust10={"trust_feedback_strength": 0.}, trust01={"trust_update_rate": 0.},
                  trust00={"trust_update_rate": 0., "trust_feedback_strength": 0.})
    # The registered base is trust11 and the common donor for fixed-plan replay.
    result = {"baseline": {}, **result}
    for changes in result.values():
        replace(config, **changes)
    return result


def resolve_design(spec):
    fields = {"stage", "formal_ready", "model", "alphas", "seeds", "administrative_delays",
              "observation_delays", "scheduling_capacities", "dynamics"}
    require(isinstance(spec, dict) and set(spec) == fields, "Unknown or missing S1 fields")
    require(spec["stage"] == "S1" and spec["formal_ready"] is False, "S1 development only")
    cfg = ResearchConfig.from_dict(spec["model"])
    require(cfg.response_enabled and not cfg.full_heat_off and cfg.trust_update_rate > 0
            and cfg.trust_feedback_strength > 0, "S1 baseline requires active response, heat, trust update and feedback")
    for key, lower in (("seeds", 0), ("administrative_delays", 0), ("observation_delays", 0),
                       ("scheduling_capacities", 1)):
        values = spec[key]
        require(isinstance(values, list) and values and all(type(v) is int and v >= lower for v in values)
                and len(set(values)) == len(values), f"Invalid {key}")
    require(0 in spec["administrative_delays"] and any(v > 0 for v in spec["administrative_delays"]),
            "S1 needs zero and positive delay")
    alphas = spec["alphas"]
    require(isinstance(alphas, list) and alphas and all(type(a) in (int, float) and np.isfinite(a)
            and 0 <= a <= 1 for a in alphas) and len(set(alphas)) == len(alphas), "Invalid alphas")
    require(isinstance(spec["dynamics"], dict), "Invalid dynamics specification")
    # Validate the dynamic registration without running a simulation.
    from .research_dynamics import resolve_dynamics_spec
    jobs = []
    for index, alpha in enumerate(alphas):
        model = replace(cfg, alpha=alpha)
        conditions = closed_conditions(model, spec)
        for seed in spec["seeds"]:
            jobs.append({"kind": "mechanisms", "group_id": f"a{index:02d}_seed{seed}", "seed": seed,
                         "alpha": alpha, "model": model.to_dict(), "conditions": conditions,
                         "delays": spec["administrative_delays"]})
    for seed in spec["seeds"]:
        dynamic_spec = resolve_dynamics_spec(cfg, seed, spec["dynamics"])
        require(dynamic_spec["reference_seed"] not in spec["seeds"], "Healthy reference seed must be independent")
        jobs.append({"kind": "dynamics", "group_id": f"dynamics_seed{seed}", "seed": seed,
                     "model": cfg.to_dict(), "spec": dynamic_spec})
    return jsonable(jobs)


def event_diagnostics(state):
    """Evaluator-only event clocks; actual used evidence stays distinct from latest delivery."""
    result = []
    for event in state["logs"]["events"]:
        trigger, executed = event["trigger_step"], event["execution_step"]
        estimate = state["logs"]["government_estimates"][trigger]
        used = estimate["estimate_input_packet_id"]
        packet = state["packet_index"].get(used) if used else None
        vector = [int(k == event["topic"]) for k in range(state["config"]["n_topics"])]
        result.append({"event_id": event["event_id"], "target_vector": vector,
                       "decision_at": trigger, "due_at": event["due_step"], "executed_at": executed,
                       "waiting_time": None if executed is None else executed - trigger,
                       "censor_time": state["tick"] - 1 - trigger if executed is None else None,
                       "receiver_estimate_updated_at": estimate["estimate_updated_at"],
                       "receiver_used_packet_id": used, "receiver_signal_end": packet["window_end"] if packet else None,
                       "receiver_signal_available_at": packet["available_at"] if packet else None,
                       "plan_information_ref": event["information_ref"],
                       "plan_mode": "controlled_replay" if state["queue"].get("queue_mode") else "adaptive",
                       "P_trigger": event["P_trigger"], "P_execution": event["P_execution"]})
    return result


def build_derived(state, metadata):
    summary = summarize_world(state["logs"]["trajectory"], state["logs"]["events"], metadata["analysis_config"])
    rows = state["logs"]["trajectory"]
    extra = {"observed_ticks": len(rows), "max_pending": max((r["pending_count"] for r in rows), default=0),
             "scheduled_total": sum(r["responses_scheduled"] for r in rows),
             "executed_total": sum(r["responses_executed"] for r in rows),
             "final_trust_mean": rows[-1]["trust_mean"] if rows else None,
             "final_preference_shift": rows[-1]["preference_shift"] if rows else None}
    return {"run_id": metadata["run_id"], "group_id": metadata["group_id"], "scenario": metadata["scenario"],
            "condition": metadata["condition"], "summary": summary, "mechanisms": extra,
            "event_diagnostics": event_diagnostics(state)}


def save_world(world, output, batch_id, job, condition, scenario, expected_hash, provenance=None):
    require(world.code_hash == expected_hash, "Source changed during S1 run")
    run_id = f"{scenario}_{job['group_id']}_{condition}"
    folder = output / "raw" / run_id
    snapshot = world.snapshot()
    state = snapshot["state"]
    status = "complete" if world.tick == world.config.steps else "checkpoint"
    metadata = {"schema_version": "s1-artifacts-1", "engine_schema": SCHEMA_VERSION,
                "stage": "S1", "formal_ready": False, "status": status, "failure": None, "retry": 0,
                "batch_id": batch_id, "run_id": run_id, "world_id": f"{batch_id}/{run_id}",
                "engine_world_id": world.world_id, "group_id": job["group_id"], "scenario": scenario,
                "condition": condition, "code_version": RESEARCH_VERSION, "source_hash": expected_hash,
                "config": world.config.to_dict(), "config_hash": canonical_hash(world.config.to_dict()),
                "analysis_config": world.config.analysis_config(), "seed": world.seed,
                "initial_condition_id": world.initial_condition, "initial_state_hash": world.initial_state_hash,
                "parent_engine_world_id": world.parent_world_id,
                "parent_world_id": None if world.parent_world_id is None else f"{batch_id}/engine/{world.parent_world_id}",
                "engine_reference_id": f"{batch_id}/engine/{world.world_id}",
                "parent_snapshot_hash": world.snapshot_id, "final_snapshot_hash": snapshot["state_hash"],
                "fork_phase": world.phase, "treatments": world.treatments,
                "randomness": world.randomness.snapshot(), "shock_tape_kind": "addressed_randomness_not_pregenerated_tape",
                "shock_tape_id": f"{world.randomness.snapshot()['schema']}/seed{world.seed}",
                "shock_tape_hash": canonical_hash(world.randomness.snapshot()),
                "ordinary_supply_hash": canonical_hash(world.supply_log),
                "information_condition": {"PrefInfo": world.config.pref_info, "RuleInfo": world.config.rule_info},
                "taxonomy_version": f"synthetic-topics-{world.config.n_topics}-v1", "time_unit": "simulation_tick",
                "signal_schema": "public-signals-1", "outcome_schema": "research-outcomes-1",
                "provenance": provenance or {}, "evaluation_scope": "S1 technical development; no formal inference"}
    write_json(folder / "metadata.json", metadata)
    write_json(folder / "evaluator" / "snapshot.json", snapshot)
    for key, relative in LOG_FILES.items():
        write_json(folder / relative, state["logs"][key])
    write_json(folder / "government" / "actions.json",
               [{k: v for k, v in event.items() if k not in {"P_trigger", "P_execution"}} for event in world.events])
    derived = build_derived(state, metadata)
    write_json(output / "derived" / f"{run_id}.json", derived)
    return derived


def run_group(job, output_name, batch_id, expected_hash):
    output = Path(output_name)
    require(source_hash() == expected_hash, "Source changed before S1 worker")
    config = ResearchConfig.from_dict(job["model"])
    records = []
    if job["kind"] == "mechanisms":
        from .research_replay import make_replay_worlds, replay_diagnostics
        donor = ResearchWorld(config, job["seed"]).run()
        for condition, changes in job["conditions"].items():
            world = donor if condition == "baseline" else ResearchWorld(replace(config, **changes), job["seed"]).run()
            require(world.initial_state_hash == donor.initial_state_hash, "S1 paired initial state differs")
            require(world.supply_log == donor.supply_log, "S1 ordinary supply differs")
            records.append(save_world(world, output, batch_id, job, condition, "closed", expected_hash))
        replay_checks = {}
        for delay, world in make_replay_worlds(donor, job["delays"]).items():
            world.run()
            require(world.supply_log == donor.supply_log, "Replay changed ordinary supply")
            records.append(save_world(world, output, batch_id, job, f"delay{delay}", "replay", expected_hash,
                                      {"donor_run_id": f"closed_{job['group_id']}_baseline",
                                       "replay_plan_hash": world.replay_plan.plan_hash}))
            replay_checks[str(delay)] = replay_diagnostics(world)
        write_json(output / "diagnostics" / f"{job['group_id']}.json", replay_checks)
        checks = {"common_initial_state": True, "common_ordinary_supply": True, "fixed_donor_plan": True}
    else:
        from .research_dynamics import run_dynamics
        result = run_dynamics(config, job["seed"], job["spec"])
        for name, world in result["worlds"].items():
            records.append(save_world(world, output, batch_id, job, name, "dynamic", expected_hash))
        for name, snapshot in result["snapshots"].items():
            write_json(output / "dynamic_snapshots" / job["group_id"] / f"{name}.json", snapshot)
        write_json(output / "diagnostics" / f"{job['group_id']}.json", result["diagnostics"])
        checks = {"dynamic_registration_and_lineage": True}
    write_json(output / "checks" / f"{job['group_id']}.json", checks)
    return {"group_id": job["group_id"], "kind": job["kind"], "alpha": job.get("alpha"),
            "records": records, "checks": checks}


def aggregate(groups):
    output = {}
    for alpha in sorted({g["alpha"] for g in groups if g["kind"] == "mechanisms"}):
        selected = [g for g in groups if g["kind"] == "mechanisms" and g["alpha"] == alpha]
        result = {}
        for scenario in ("closed", "replay"):
            conditions = sorted({r["condition"] for g in selected for r in g["records"] if r["scenario"] == scenario})
            baseline = "baseline" if scenario == "closed" else "delay0"
            result[scenario] = {}
            for metric in METRICS:
                values = {g["group_id"]: {r["condition"]: r["summary"][metric] for r in g["records"]
                                          if r["scenario"] == scenario} for g in selected}
                contrasts = {condition: paired_contrast(values, {condition: 1, baseline: -1})
                             for condition in conditions if condition != baseline}
                if scenario == "closed":
                    contrasts["trust_interaction"] = paired_contrast(values,
                        {"baseline": 1, "trust10": -1, "trust01": -1, "trust00": 1})
                for value in contrasts.values():
                    for key in ("standard_error", "normal95_interval", "interval_method"):
                        value.pop(key, None)
                    value["scope"] = "S1 descriptive pairing, not a precision pilot or formal effect"
                result[scenario][metric] = contrasts
        output[str(alpha)] = result
    return output


def run_study(spec, output, workers=1):
    jobs = resolve_design(spec)
    require(type(workers) is int and workers >= 1, "Invalid workers")
    output = Path(output)
    require(not output.exists(), "Output must not exist; preserve all historical batches")
    output.mkdir(parents=True)
    expected_hash = source_hash()
    batch_id = f"s1-{uuid.uuid4().hex}"
    manifest = {"batch_id": batch_id, "stage": "S1", "formal_ready": False, "status": "running",
                "code_version": RESEARCH_VERSION, "schema_version": "s1-artifacts-1", "source_hash": expected_hash,
                "specification": spec, "specification_hash": canonical_hash(spec), "workers": workers,
                "python": sys.version, "numpy": np.__version__, "platform": platform.platform(),
                "started_at": datetime.now(timezone.utc).isoformat(), "expected_groups": len(jobs)}
    write_json(output / "launch_manifest.json", manifest)
    write_json(output / "configuration.json", spec)
    write_json(output / "resolved_design.json", jobs)
    for folder in ("abm_jasss", "scripts", "tests"):
        for path in sorted((ROOT / folder).glob("*.py")):
            target = output / "source_snapshot" / folder / path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    for name in ("requirements.txt", "formal_experiment_protocol.md", "signal_and_outcome_contract.md",
                 "s1_execution_protocol_20260929.md", "ODD_research.md"):
        shutil.copyfile(ROOT / name, output / "source_snapshot" / name)
    manifest["source_sha256"] = {p.name: file_hash(p) for p in sorted((output / "source_snapshot" / "abm_jasss").glob("*.py"))}
    require(canonical_hash(manifest["source_sha256"]) == expected_hash, "Source changed while archiving")
    groups, failures = [], []
    if workers == 1:
        for job in jobs:
            try:
                groups.append(run_group(job, str(output), batch_id, expected_hash))
            except Exception:
                failures.append({"group_id": job["group_id"], "traceback": traceback.format_exc()})
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(run_group, job, str(output), batch_id, expected_hash): job for job in jobs}
            for future in as_completed(futures):
                try:
                    groups.append(future.result())
                except Exception:
                    failures.append({"group_id": futures[future]["group_id"], "traceback": traceback.format_exc()})
    if source_hash() != expected_hash:
        failures.append({"group_id": None, "error": "Source changed during S1 execution"})
    groups.sort(key=lambda g: g["group_id"])
    manifest.update(status="failed" if failures else "complete", completed_groups=len(groups),
                    failed_groups=len(failures), finished_at=datetime.now(timezone.utc).isoformat())
    if failures:
        write_json(output / "failures.json", failures)
    else:
        manifest["world_records"] = sum(len(g["records"]) for g in groups)
        write_json(output / "paired_diagnostics.json", aggregate(groups))
        write_json(output / "validation.json", {"stage": "S1", "formal_ready": False, "status": "passed",
                   "groups": [{"group_id": g["group_id"], "kind": g["kind"], "run_ids": [r["run_id"] for r in g["records"]],
                               "checks": g["checks"]} for g in groups]})
    write_json(output / "manifest.json", manifest)
    write_json(output / "artifact_hashes.json", {p.relative_to(output).as_posix(): file_hash(p)
               for p in sorted(output.rglob("*")) if p.is_file()})
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    try:
        result = run_study(json.loads(args.config.read_text(encoding="utf-8-sig")), args.output, args.workers)
    except (ValueError, TypeError, OSError) as error:
        parser.exit(2, f"{error}\n")
    print(json.dumps({k: result[k] for k in ("status", "stage", "formal_ready", "completed_groups", "failed_groups")}))
    if result["status"] != "complete":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
