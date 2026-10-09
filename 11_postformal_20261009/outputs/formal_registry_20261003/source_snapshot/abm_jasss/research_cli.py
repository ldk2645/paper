"""Reproducible S0 development runs; this entry point cannot run formal studies."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import shutil
import sys
import traceback
import uuid

import numpy as np

from .research_config import ResearchConfig, RESEARCH_VERSION, SCHEMA_VERSION
from .research_outcomes import paired_contrast, summarize_world
from .research_world import ResearchWorld, canonical_hash, source_hash

ROOT = Path(__file__).resolve().parents[1]
CELLS = {"I00": (False, False), "I10": (True, False),
         "I01": (False, True), "I11": (True, True)}
METRICS = ("platform_representation_gap", "perception_error",
           "targeting_error_trigger", "targeting_error_execution", "exposure_gap", "waiting_time",
           "response_completion_L", "execution_coverage")


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    # All output paths are new; exclusive creation also catches duplicate IDs.
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def resolve_design(spec):
    expected = {"stage", "formal_ready", "model", "alphas", "seeds", "fork_tick", "branches"}
    require(isinstance(spec, dict) and set(spec) == expected, "Unknown or missing S0 specification fields")
    require(spec["stage"] == "S0" and spec["formal_ready"] is False,
            "Only S0 development runs with formal_ready=false are supported")
    cfg = ResearchConfig.from_dict(spec["model"])
    require(not cfg.pref_info and not cfg.rule_info, "The common base must have I00 information")
    tick = spec["fork_tick"]
    require(type(tick) is int and 0 < tick < cfg.steps, "fork_tick must be inside the horizon")
    require(cfg.final_window <= cfg.steps - tick, "Evaluation window must be entirely after the fork")
    require(cfg.response_enabled, "S0 B0 retains active government responses")
    alphas, seeds = spec["alphas"], spec["seeds"]
    require(isinstance(alphas, list) and alphas and all(type(a) in (int, float)
            and np.isfinite(a) and 0 <= a <= 1 for a in alphas), "Invalid alpha list")
    require(len(set(alphas)) == len(alphas), "Duplicate alpha")
    require(isinstance(seeds, list) and seeds and all(type(s) is int and s >= 0 for s in seeds),
            "Invalid development seeds")
    require(len(set(seeds)) == len(seeds), "Duplicate development seed")
    branches = spec["branches"]
    require(isinstance(branches, dict) and set(branches) == {"B0", "B1", "B2", "B3", "B4"},
            "S0 requires exactly the five registered branches B0-B4")
    require(branches["B0"] == {} and branches["B1"] == {"pref_info": True}, "Invalid B0/B1 intervention")
    require(set(branches["B2"]) == {"government_delay"}, "B2 changes only administrative delay")
    require(set(branches["B3"]) == {"response_capacity"}, "B3 changes only scheduling capacity")
    require(set(branches["B4"]) in ({"alpha"}, {"ranking"}), "B4 changes one ranking setting")
    require(branches["B2"]["government_delay"] < cfg.government_delay, "B2 must reduce delay")
    require(branches["B3"]["response_capacity"] > cfg.response_capacity, "B3 must increase capacity")
    for changes in branches.values():
        replace(cfg, **changes)
    for alpha in alphas:
        changed = replace(cfg, alpha=alpha, **{k: v for k, v in branches["B4"].items() if k != "alpha"})
        require(branches["B4"].get("alpha", changed.alpha) != alpha
                or changed.ranking != cfg.ranking, "B4 must change the ranking in every stratum")
    jobs = []
    for index, alpha in enumerate(alphas):
        for seed in seeds:
            group = f"a{index:02d}_seed{seed}"
            model = replace(cfg, alpha=alpha).to_dict()
            # Resolve and validate the independent E4 enrollment window now.
            branch_model = dict(model, completion_start=max(cfg.completion_start, tick))
            analysis = ResearchConfig.from_dict(branch_model).analysis_config()
            require(analysis["completion_start"] <= analysis["completion_end"] < cfg.steps,
                    "E4 completion cohort must fit after fork_tick")
            jobs.append({"group_id": group, "seed": seed, "alpha": alpha,
                         "model": model, "fork_tick": tick, "branches": branches})
    return jobs


def validate_world(world, analysis_config=None):
    """Check cross-layer references before publishing any successful summary."""
    c = world.config
    require([r["step"] for r in world.trajectory] == list(range(c.steps)), "Incomplete trajectory")
    require(len(world.information_log) == len(world.government_estimates) == c.steps,
            "Missing government records")
    for row, info, estimate in zip(world.trajectory, world.information_log, world.government_estimates):
        tick = row["step"]
        packet = info["public_packet"]
        if packet is not None:
            require(packet["available_at"] <= tick and packet["window_end"] < tick,
                    "Government consumed future or undelivered information")
            require(packet["packet_id"] in world.packet_index, "Unknown available packet")
        for key in ("survey", "rule"):
            value = info[key]
            if value is not None:
                require(value["available_at"] <= tick, "Undelivered auxiliary information")
        # Access may change at an E4 fork; use the recorded treatment time.
        pref = c.pref_info
        for treatment in world.treatments:
            if "pref_info" in treatment["changes"] and tick < treatment["at"]:
                pref = False  # S0 mothers are always I00.
        require(pref or info["survey"] is None, "Survey leaked into an unpermitted condition")
        require(c.rule_info or info["rule"] is None, "Ranking rule leaked into an opaque condition")
        require(row["available_packet_id"] == (None if packet is None else packet["packet_id"]),
                "Available packet reference disagrees")
        used_id = estimate["estimate_input_packet_id"]
        require(used_id is None or used_id in world.packet_index, "Unknown used packet")
        require(row["estimate_input_packet_id"] == used_id, "Used packet reference disagrees")
        updated_at = estimate["estimate_updated_at"]
        require(updated_at is None or updated_at <= tick, "Estimate timestamp lies in the future")
        if used_id is not None:
            used = world.packet_index[used_id]
            require(updated_at is not None and used["available_at"] <= updated_at
                    and used["window_end"] < updated_at, "Estimate used unavailable evidence")
    pending = {p["event_id"] for p in world.queue.pending.values()}
    require(pending == {e["event_id"] for e in world.events if e["execution_step"] is None},
            "Pending queue and event ledger disagree")
    for event in world.events:
        executed = event["execution_step"]
        require(executed is None or executed == event["due_step"], "Action did not execute at its due tick")
        require(executed is not None or event["due_step"] >= c.steps, "Overdue action at end of run")
        ref = event["information_ref"]
        info = world.information_log[ref["estimate_record"]]
        require(canonical_hash(info) == ref["information_hash"], "Action information reference changed")
    return summarize_world(world.trajectory, world.events, analysis_config or c.analysis_config())


def save_world(world, output, batch_id, run_id, group_id, scenario, condition, expected_hash):
    require(world.code_hash == expected_hash, "Source changed during run")
    analysis_config = world.config.analysis_config()
    if scenario == "E4":
        analysis_config = replace(world.config, completion_start=max(
            world.config.completion_start, world.treatments[-1]["at"])).analysis_config()
    summary = validate_world(world, analysis_config)
    folder = output / "raw" / run_id
    folder.mkdir(parents=True, exist_ok=False)
    metadata = {"schema_version": SCHEMA_VERSION, "batch_id": batch_id,
                "world_id": f"{batch_id}/{run_id}", "engine_world_id": world.world_id,
                "run_id": run_id, "group_id": group_id, "scenario": scenario, "condition": condition,
                "code_version": RESEARCH_VERSION, "source_hash": expected_hash,
                "config": world.config.to_dict(), "config_hash": canonical_hash(world.config.to_dict()),
                "analysis_config": analysis_config, "seed": world.seed,
                "initial_condition": world.initial_condition, "initial_state_hash": world.initial_state_hash,
                "parent_world_id": f"{batch_id}/E2_{group_id}_I00" if scenario == "E4" else None,
                "snapshot_id": world.snapshot_id, "fork_tick": world.treatments[-1]["at"] if world.treatments else None,
                "fork_phase": world.phase if world.treatments else None,
                "treatments": world.treatments, "randomness": world.randomness.snapshot(),
                "shock_address_hash": canonical_hash(world.randomness.snapshot()),
                "ordinary_supply_hash": canonical_hash(world.supply_log),
                "information_condition": {"PrefInfo": world.config.pref_info, "RuleInfo": world.config.rule_info},
                "taxonomy_version": f"synthetic-topics-{world.config.n_topics}-v1",
                "time_unit": "simulation_tick", "signal_schema": "public-signals-1",
                "outcome_schema": "research-outcomes-1", "status": "complete", "retry": 0,
                "formal_ready": False, "evaluation_scope": "S0 development diagnostics only"}
    write_json(folder / "metadata.json", metadata)
    write_json(folder / "public_signal_ticks.json", world.public_signal_ticks)
    write_json(folder / "observation_packets.json", {"generated": list(world.packet_index.values()),
               "received": world.observation_packets, "pending": world.pending_packets})
    write_json(folder / "government" / "information.json", world.information_log)
    write_json(folder / "government" / "estimates.json", world.government_estimates)
    # Evaluator-only latent preferences never enter the government's replay log.
    write_json(folder / "government" / "actions.json",
               [{k: v for k, v in event.items() if k not in {"P_trigger", "P_execution"}} for event in world.events])
    write_json(folder / "evaluator" / "trajectory.json", world.trajectory)
    write_json(folder / "evaluator" / "response_events.json", world.events)
    write_json(folder / "supply.json", world.supply_log)
    write_json(folder / "publications.json", world.publication_log)
    write_json(folder / "surveys.json", world.survey_log)
    write_json(folder / "snapshot_final.json", world.snapshot())
    result = {"run_id": run_id, "group_id": group_id, "scenario": scenario,
              "condition": condition, "summary": summary}
    write_json(output / "derived" / f"{run_id}.json", result)
    return result


def run_group(job, output_name, batch_id, expected_hash):
    output = Path(output_name)
    require(source_hash() == expected_hash, "Source changed before worker execution")
    cfg = ResearchConfig.from_dict(job["model"])
    group, seed, tick = job["group_id"], job["seed"], job["fork_tick"]
    results, checks = [], {}
    mother = ResearchWorld(cfg, seed).run(tick)
    snapshot = mother.snapshot()
    write_json(output / "snapshots" / f"{group}.json", snapshot)
    restored = ResearchWorld.from_snapshot(json.loads(json.dumps(snapshot, allow_nan=False))).run()
    mother.run()
    require(restored.snapshot() == mother.snapshot(), "Snapshot continuation differs from uninterrupted execution")
    checks["snapshot_continuation_equal"] = True
    initial_hash = mother.initial_state_hash
    for condition, (pref, rule) in CELLS.items():
        world = mother if condition == "I00" else ResearchWorld(replace(cfg, pref_info=pref, rule_info=rule), seed).run()
        require(world.initial_state_hash == initial_hash, "E2 physical initial states differ")
        require(world.supply_log == mother.supply_log, "E2 ordinary exogenous supply differs")
        results.append(save_world(world, output, batch_id, f"E2_{group}_{condition}", group,
                                  "E2", condition, expected_hash))
    checks["e2_common_initial_state_and_supply"] = True
    parent = ResearchWorld.from_snapshot(snapshot)
    frozen_parent = parent.snapshot()
    inherited = parent.queue.snapshot()["pending"]
    for condition, changes in sorted(job["branches"].items()):
        branch = parent.fork(condition, changes)
        require(branch.queue.snapshot()["pending"] == inherited, "Intervention rewrote an inherited plan")
        require(branch.treatments[-1]["pre_treatment_state_hash"] == snapshot["state_hash"], "Fork states differ")
        require(parent.snapshot() == frozen_parent, "Fork modified parent state")
        branch.run()
        require(parent.snapshot() == frozen_parent, "Branch execution contaminated parent")
        require(branch.supply_log == mother.supply_log, "Branch changed ordinary exogenous content")
        if condition == "B0":
            for key in ResearchWorld.LOG_FIELDS:
                if key != "treatments":
                    require(getattr(branch, key) == getattr(mother, key), f"B0 continuation differs: {key}")
            checks["b0_logs_equal_uninterrupted"] = True
        # Completion cohorts enroll new plans after treatment; targeting retains
        # any inherited action executed in the fixed terminal evaluation window.
        results.append(save_world(branch, output, batch_id, f"E4_{group}_{condition}", group,
                                  "E4", condition, expected_hash))
    checks.update(fork_parent_isolation=True, inherited_plans_unchanged=True,
                  branch_pre_treatment_hash_equal=True, branch_ordinary_supply_equal=True)
    write_json(output / "checks" / f"{group}.json", checks)
    return {"group_id": group, "alpha": job["alpha"], "results": results, "checks": checks}


def aggregate(groups):
    """Descriptive paired diagnostics per alpha; S0 is not a precision pilot."""
    output = {}
    for alpha in sorted({g["alpha"] for g in groups}):
        strata = [g for g in groups if g["alpha"] == alpha]
        result = {}
        for scenario in ("E2", "E4"):
            result[scenario] = {}
            for metric in METRICS:
                values = {g["group_id"]: {r["condition"]: r["summary"][metric]
                          for r in g["results"] if r["scenario"] == scenario} for g in strata}
                contrasts = (paired_contrast(values) if scenario == "E2" else
                             {branch: paired_contrast(values, {branch: 1, "B0": -1})
                              for branch in ("B1", "B2", "B3", "B4")})
                for value in contrasts.values():
                    for key in ("normal95_interval", "standard_error", "interval_method"):
                        value.pop(key, None)
                    value["scope"] = "S0 descriptive pairing and missingness only; no inferential claim"
                result[scenario][metric] = contrasts
        output[str(alpha)] = result
    return output


def run_study(spec, output, workers=1):
    jobs = resolve_design(spec)
    require(type(workers) is int and workers >= 1, "workers must be positive")
    output = Path(output)
    require(not output.exists(), "Output path must not exist; historical files are never overwritten")
    output.mkdir(parents=True, exist_ok=False)
    batch_id = f"s0-{uuid.uuid4().hex}"
    expected_hash = source_hash()
    manifest = {"batch_id": batch_id, "stage": "S0", "formal_ready": False,
                "code_version": RESEARCH_VERSION, "schema_version": SCHEMA_VERSION,
                "status": "running", "started_at": datetime.now(timezone.utc).isoformat(),
                "source_hash": expected_hash, "specification": spec, "specification_hash": canonical_hash(spec),
                "python": sys.version, "numpy": np.__version__, "platform": platform.platform(),
                "workers": workers, "expected_groups": len(jobs), "expected_world_records": 9 * len(jobs),
                "scope": "Development technical validation; not formal, precision, or empirical evidence"}
    # Preserve the launch record; the final status is a separate immutable file.
    write_json(output / "launch_manifest.json", manifest)
    write_json(output / "resolved_design.json", jobs)
    write_json(output / "configuration.json", spec)
    source_files = {}
    for path in sorted((ROOT / "abm_jasss").glob("*.py")):
        destination = output / "source_snapshot" / "abm_jasss" / path.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
        source_files[path.name] = file_hash(destination)
    require(canonical_hash(source_files) == expected_hash, "Source changed while snapshotting code")
    for folder in ("tests", "scripts"):
        for path in sorted((ROOT / folder).glob("*.py")):
            destination = output / "source_snapshot" / folder / path.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
    for name in ("requirements.txt", "formal_experiment_protocol.md", "signal_and_outcome_contract.md"):
        shutil.copyfile(ROOT / name, output / "source_snapshot" / name)
    manifest["source_sha256"] = source_files
    groups, failures = [], []
    if workers == 1:
        for job in jobs:
            try:
                groups.append(run_group(job, str(output), batch_id, expected_hash))
            except Exception:
                failures.append({"group_id": job["group_id"], "traceback": traceback.format_exc()})
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(run_group, job, str(output), batch_id, expected_hash): job for job in jobs}
            for future in as_completed(futures):
                try:
                    groups.append(future.result())
                except Exception:
                    failures.append({"group_id": futures[future]["group_id"], "traceback": traceback.format_exc()})
    if source_hash() != expected_hash:
        failures.append({"group_id": None, "error": "Source changed during run"})
    groups.sort(key=lambda g: g["group_id"])
    if failures:
        write_json(output / "failures.json", failures)
        manifest.update(status="failed", failed_groups=len(failures), completed_groups=len(groups))
    else:
        write_json(output / "paired_diagnostics.json", aggregate(groups))
        validation = {"status": "passed", "stage": "S0", "formal_ready": False,
                      "groups": len(groups), "e2_worlds": 4 * len(groups), "e4_suffixes": 5 * len(groups),
                      "checks": {g["group_id"]: g["checks"] for g in groups},
                      "scope": "Cross-layer records, pairing, continuation and artifact generation",
                      "not_claimed": ["Complete S1", "Precision target", "Formal design freeze", "Empirical validity"]}
        write_json(output / "validation.json", validation)
        lines = ["# 0.5.0-dev S0 开发验收", "",
                 f"四信息条件共 {4 * len(groups)} 个世界；{len(groups)} 个 I00 母状态各分五支，共 {5 * len(groups)} 条后缀。",
                 "", "状态恢复、B0 连续轨迹、分支隔离、既有队列继承和普通外生内容配对检查通过。",
                 "公开信号、合法政府输入、估计、评价轨迹与事件分别保存；缺失值保持 null。",
                 "", "配置在 launch_manifest.json/configuration.json 中登记；源码与测试保存在 source_snapshot。",
                 "artifact_hashes.json 可核查产物完整性，paired_diagnostics.json 仅报告配对描述与共同支持。",
                 "", "formal_ready=false。此批不是精度 pilot，也不提供相变、干预有效性或经验验证结论。",
                 "仍需 S1 完整验收、E3 固定计划回放、动态协议、独立精度 pilot 和正式配置/新种子冻结。", ""]
        (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
        manifest.update(status="complete", failed_groups=0, completed_groups=len(groups),
                        world_records=9 * len(groups))
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    write_json(output / "manifest.json", manifest)
    hashes = {p.relative_to(output).as_posix(): file_hash(p) for p in sorted(output.rglob("*")) if p.is_file()}
    write_json(output / "artifact_hashes.json", hashes)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    try:
        spec = json.loads(args.config.read_text(encoding="utf-8-sig"))
        result = run_study(spec, args.output, args.workers)
    except (ValueError, TypeError, OSError) as exc:
        parser.exit(2, f"{exc}\n")
    print(json.dumps({k: result[k] for k in ("status", "stage", "formal_ready", "completed_groups")}))
    if result["status"] != "complete":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
