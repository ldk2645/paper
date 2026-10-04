"""Independent, fixed-budget precision pilot; keeps the S1 engine unchanged."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import platform
import shutil
import sys
import time
import traceback
import uuid

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from abm_jasss.research_cli import require, write_json, file_hash
from abm_jasss.research_config import ResearchConfig, RESEARCH_VERSION
from abm_jasss.research_world import ResearchWorld, canonical_hash, jsonable, source_hash
from scripts.validate_s1_outputs import read

PRIMARY = ["platform_representation_gap", "perception_error", "targeting_error_trigger"]
E2 = {"I00": {}, "I10": {"pref_info": True}, "I01": {"rule_info": True},
      "I11": {"pref_info": True, "rule_info": True}}
CLOSED = {"delay0": {"government_delay": 0}, "delay1": {"government_delay": 1},
          "delay10": {"government_delay": 10}, "capacity2": {"response_capacity": 2},
          "observation2": {"observation_delay": 2}}
CONTRASTS = {
    "E2": {"pref_given_rule0": {"I10": 1, "I00": -1},
           "pref_given_rule1": {"I11": 1, "I01": -1},
           "rule_given_pref0": {"I01": 1, "I00": -1},
           "rule_given_pref1": {"I11": 1, "I10": -1},
           "interaction": {"I11": 1, "I10": -1, "I01": -1, "I00": 1}},
    "E3_closed": {name: {name: 1, "baseline": -1} for name in CLOSED},
    "E3_replay": {f"delay{d}": {f"delay{d}": 1, "delay0": -1} for d in (1, 3, 10)},
    "E4": {f"B{i}": {f"B{i}": 1, "B0": -1} for i in range(1, 5)},
}


def resolve_design(spec, wave):
    fields = {"stage", "formal_ready", "model", "alphas", "initial_seeds", "expansion_seeds",
              "fork_tick", "branches", "precision", "stability", "expected_source_hash"}
    require(set(spec) == fields, "Unknown/missing precision specification fields")
    require(spec["stage"] == "precision_pilot" and spec["formal_ready"] is False,
            "Independent precision pilot only")
    require(wave in ("initial", "expansion"), "Unknown pilot wave")
    cfg = ResearchConfig.from_dict(spec["model"])
    require(not cfg.pref_info and not cfg.rule_info and cfg.response_enabled,
            "Pilot mother must be active I00")
    require(cfg.government_delay == 3 and cfg.response_capacity == 1 and cfg.observation_delay == 0,
            "Registered E3 baseline is delay3/capacity1/observation0")
    require(0 < spec["fork_tick"] <= cfg.steps - cfg.final_window, "Invalid fork/evaluation window")
    require(cfg.completion_start >= spec["fork_tick"] and
            cfg.analysis_config()["completion_end"] + cfg.completion_followup < cfg.steps,
            "Completion enrollment must follow the fork and allow full follow-up")
    alphas = spec["alphas"]
    require(alphas and len(set(alphas)) == len(alphas) and
            all(type(a) in (int, float) and np.isfinite(a) and 0 <= a <= 1 for a in alphas), "Invalid alphas")
    seeds = spec["initial_seeds"] + spec["expansion_seeds"]
    require(all(type(s) is int and s >= 0 for s in seeds) and len(set(seeds)) == len(seeds)
            and len(spec["initial_seeds"]) == len(spec["expansion_seeds"]) > 0, "Invalid/disjoint seed waves")
    require(cfg.reference_seed not in seeds, "Synthetic reference seed overlaps mother seeds")
    branches = spec["branches"]
    require(branches == {"B0": {}, "B1": {"pref_info": True}, "B2": {"government_delay": 1},
                         "B3": {"response_capacity": 2}, "B4": {"alpha": 0.}}, "Unregistered E4 branches")
    require(all(a != 0 for a in alphas), "B4 must change alpha")
    require(set(spec["precision"]) == {"target_half_width", "min_valid", "max_total"}, "Invalid precision keys")
    p = spec["precision"]
    require(np.isfinite(p["target_half_width"]) and p["target_half_width"] > 0 and
            type(p["min_valid"]) is int and type(p["max_total"]) is int and
            2 <= p["min_valid"] <= p["max_total"], "Invalid precision budget")
    require(spec["stability"] == {"variance_relative_tolerance": .25, "support_absolute_tolerance": .10},
            "Unregistered stability diagnostics")
    return [{"group_id": f"a{i:02d}_seed{seed}", "seed": seed, "alpha": alpha,
             "model": replace(cfg, alpha=alpha).to_dict(), "fork_tick": spec["fork_tick"],
             "branches": branches} for i, alpha in enumerate(alphas) for seed in spec[wave + "_seeds"]]


def analysis_spec(spec, parent_ids):
    return {"alphas": spec["alphas"], "parent_ids": parent_ids, "metrics": PRIMARY,
            "contrasts": CONTRASTS, **spec["precision"]}


def statistical_records(output, jobs):
    records = []
    for job in jobs:
        for folder in sorted((Path(output) / "raw").glob("*" + job["group_id"] + "_*")):
            meta = read(folder / "metadata.json")
            derived = read(Path(output) / "derived" / (meta["run_id"] + ".json"))
            record = {"family": meta["scenario"], "alpha": job["alpha"], "parent_id": job["seed"],
                      "arm": meta["condition"], "metrics": {key: derived["summary"][key] for key in PRIMARY},
                      "status": meta["status"]}
            records.append(record)
            if record["family"] == "E2" and record["arm"] == "I00":
                records.append(dict(record, family="E3_closed", arm="baseline"))
    return records


def run_group(job, output_name, batch_id, expected_hash):
    from scripts.precision_artifacts import save_world, write_gzip_json
    from abm_jasss.research_replay import make_replay_worlds, replay_diagnostics
    output = Path(output_name)
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
                   analysis_config=world.config.analysis_config(), provenance=provenance)
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


def run_study(spec, output, wave="initial", workers=3):
    jobs = resolve_design(spec, wave)
    require(type(workers) is int and workers >= 1, "Invalid workers")
    require(source_hash() == spec["expected_source_hash"], "S1 engine source changed")
    output = Path(output)
    require(not output.exists(), "Output already exists; preserve immutable batches")
    output.mkdir(parents=True)
    started = time.monotonic()
    batch_id = "precision_" + uuid.uuid4().hex
    archived = {}
    for directory in ("abm_jasss", "scripts", "tests"):
        for path in sorted((ROOT / directory).glob("*.py")):
            destination = output / "source_snapshot" / directory / path.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
            if directory == "abm_jasss":
                archived[path.name] = file_hash(path)
    for name in ("requirements.txt", "precision_pilot_protocol_20260930.md", "formal_experiment_protocol.md",
                 "signal_and_outcome_contract.md", "ODD_research.md"):
        require((ROOT / name).is_file(), f"Missing required provenance: {name}")
        shutil.copyfile(ROOT / name, output / "source_snapshot" / name)
    require(canonical_hash(archived) == spec["expected_source_hash"], "Archive engine hash differs")
    manifest = {"schema_version": "precision-batch-1", "stage": "precision_pilot", "formal_ready": False,
                "batch_id": batch_id, "wave": wave, "status": "running", "workers": workers,
                "created_at": datetime.now(timezone.utc).isoformat(), "code_version": RESEARCH_VERSION,
                "source_hash": spec["expected_source_hash"], "source_sha256": archived,
                "specification": spec, "specification_hash": canonical_hash(spec),
                "python": platform.python_version(), "numpy": np.__version__, "expected_groups": len(jobs)}
    write_json(output / "configuration.json", spec)
    write_json(output / "resolved_design.json", jobs)
    write_json(output / "launch_manifest.json", manifest)
    results, failures = [], []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        pending = {pool.submit(run_group, j, str(output), batch_id, spec["expected_source_hash"]): j for j in jobs}
        for future in as_completed(pending):
            job = pending[future]
            try:
                results.append(future.result())
                print(f"{wave}: {len(results)}/{len(jobs)} complete {job['group_id']}", flush=True)
            except Exception:
                failures.append({"group_id": job["group_id"], "traceback": traceback.format_exc()})
                print(f"{wave}: FAILED {job['group_id']}", flush=True)
    write_json(output / "failures.json", failures)
    if not failures:
        from scripts.precision_statistics import build_precision_analysis
        records = statistical_records(output, jobs)
        write_json(output / "statistical_records.json", records)
        write_json(output / "precision_analysis.json", build_precision_analysis(
            records, analysis_spec(spec, spec[wave + "_seeds"])))
    require(source_hash() == manifest["source_hash"], "Engine source changed during pilot")
    manifest.update(status="failed" if failures else "complete", completed_groups=len(results),
                    failed_groups=len(failures), complete_records=sum(len(g["run_ids"]) for g in results),
                    elapsed_seconds=time.monotonic() - started)
    write_json(output / "manifest.json", manifest)
    write_json(output / "artifact_hashes.json", {p.relative_to(output).as_posix(): file_hash(p)
               for p in sorted(output.rglob("*")) if p.is_file()})
    require(not failures, f"Pilot failed in {len(failures)} groups; preserved failures, no analysis released")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--wave", choices=("initial", "expansion"), default="initial")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    result = run_study(read(Path(args.config)), Path(args.output), args.wave, args.workers)
    print(f"Complete: {result['complete_records']} records; {result['elapsed_seconds']:.1f}s", flush=True)


if __name__ == "__main__":
    main()
