"""Batch runner. Uses run-level paired inference; never treats time steps as replicates."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import platform
import shutil
import sys
import time
import traceback

import numpy as np

from . import __version__
from .model import ARMS, Config, simulate, summarize


def write_csv(path, rows):
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def task(config, seed, output, run_id, save_series):
    started = time.perf_counter()
    result = simulate(config, seed)
    if save_series:
        write_csv(Path(output) / "trajectories" / f"{run_id}.csv", result["rows"])
    (Path(output) / "events" / f"{run_id}.json").write_text(json.dumps({
        "events": result["events"], "storm_episodes": result["storm_episodes"],
        "pending_responses": result["pending_responses"]}, indent=2), encoding="utf-8")
    return {"run_id": run_id, "seconds": time.perf_counter() - started,
            "summary": summarize(result), "config": result["config"], "seed": seed}


def bootstrap_mean(values, rng, draws=2000):
    values = np.asarray(values, dtype=float)
    if len(values) < 2:
        return None, None
    means = rng.choice(values, size=(draws, len(values)), replace=True).mean(axis=1)
    return tuple(float(v) for v in np.quantile(means, [0.025, 0.975]))


def aggregate(rows, analysis_seed=90210):
    rng = np.random.default_rng(analysis_seed)
    grouped, contrasts = [], []
    for alpha in sorted({r["alpha"] for r in rows}):
        subset = [r for r in rows if r["alpha"] == alpha]
        by_arm = {arm: {r["seed"]: r for r in subset if r["arm"] == arm} for arm in ARMS}
        for arm in ARMS:
            values = [r["mean_error"] for _, r in sorted(by_arm[arm].items())]
            if not values:
                continue
            low, high = bootstrap_mean(values, rng)
            grouped.append({"alpha": alpha, "arm": arm, "n_runs": len(values),
                            "mean_error": float(np.mean(values)), "ci_low": low, "ci_high": high,
                            "mcse": float(np.std(values, ddof=1) / np.sqrt(len(values))) if len(values) > 1 else None})
        for arm in ARMS[1:]:
            common = sorted(set(by_arm[arm]) & set(by_arm["platform"]))
            if not common:
                continue
            diff = [by_arm[arm][s]["mean_error"] - by_arm["platform"][s]["mean_error"] for s in common]
            low, high = bootstrap_mean(diff, rng)
            contrasts.append({"alpha": alpha, "contrast": f"{arm}-platform", "n_pairs": len(common),
                              "mean_difference": float(np.mean(diff)), "ci_low": low, "ci_high": high})
    return grouped, contrasts


def aggregate_governance(rows, analysis_seed=90211):
    """Separate agenda, public-preference, response and trust outcomes by seed."""
    metrics = ("agenda_attention_share", "agenda_gap", "agenda_shortfall", "agenda_share_variance",
               "attention_error", "preference_change", "storm_fraction", "trust_mean", "trust_change",
               "trust_spread", "official_exposure_share", "response_exposure_share",
               "responses_scheduled", "responses_executed", "responses_pending_at_end", "longest_observed_storm")
    rng = np.random.default_rng(analysis_seed)
    output = []
    for alpha in sorted({r["alpha"] for r in rows}):
        for arm in ARMS:
            group = sorted((r for r in rows if r["alpha"] == alpha and r["arm"] == arm), key=lambda r: r["seed"])
            if not group:
                continue
            for metric in metrics:
                values = [r[metric] for r in group]
                low, high = bootstrap_mean(values, rng)
                output.append({"alpha": alpha, "arm": arm, "metric": metric, "n_runs": len(values),
                               "mean": float(np.mean(values)), "ci_low": low, "ci_high": high})
    return output


def svg_plot(path, grouped):
    """A self-contained, inspectable SVG; simulation outputs, not empirical evidence."""
    width, height = 840, 460
    left, top, right, bottom = 70, 60, 630, 380
    ymax = max(0.05, max((r["ci_high"] or r["mean_error"]) for r in grouped) * 1.15)
    colors = {"platform": "#2563eb", "survey": "#059669", "fused": "#d97706", "oracle": "#6b7280"}
    x = lambda v: left + v * (right - left)
    y = lambda v: bottom - v / ymax * (bottom - top)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" fill="white"/>',
             '<g font-family="Arial,sans-serif" font-size="13" fill="#222">',
             '<text x="70" y="25" font-size="18">Synthetic pilot: government inference error</text>',
             '<text x="70" y="45">Mean and pointwise 95% seed-bootstrap intervals; not confirmatory evidence</text>']
    for fraction in np.linspace(0, 1, 6):
        value = fraction * ymax
        parts.extend([f'<line x1="{left}" y1="{y(value):.2f}" x2="{right}" y2="{y(value):.2f}" stroke="#e5e7eb"/>',
                      f'<text x="60" y="{y(value)+4:.2f}" text-anchor="end">{value:.3f}</text>',
                      f'<text x="{x(fraction):.2f}" y="402" text-anchor="middle">{fraction:.1f}</text>'])
    for index, arm in enumerate(ARMS):
        entries = sorted((r for r in grouped if r["arm"] == arm), key=lambda r: r["alpha"])
        if not entries:
            continue
        points = " ".join(f'{x(r["alpha"]):.2f},{y(r["mean_error"]):.2f}' for r in entries)
        parts.append(f'<polyline points="{points}" fill="none" stroke="{colors[arm]}" stroke-width="2"/>')
        for r in entries:
            xx, yy = x(r["alpha"]), y(r["mean_error"])
            if r["ci_low"] is not None:
                parts.append(f'<line x1="{xx}" x2="{xx}" y1="{y(r["ci_low"])}" y2="{y(r["ci_high"])}" stroke="{colors[arm]}"/>')
            parts.append(f'<circle cx="{xx}" cy="{yy}" r="3" fill="{colors[arm]}"/>')
        parts.append(f'<text x="665" y="{90+index*25}" fill="{colors[arm]}">{html.escape(arm)}</text>')
    parts.extend(['<text x="310" y="435">Popularity weight alpha</text>',
                  '<text transform="translate(18,290) rotate(-90)">Total variation error</text>', '</g></svg>'])
    path.write_text("\n".join(parts), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("workers must be >=1")
    specification = json.loads(args.config.read_text(encoding="utf-8-sig"))
    base = Config(**specification["model"])
    arms = specification.get("arms", list(ARMS))
    if not arms or len(arms) != len(set(arms)) or any(a not in ARMS for a in arms):
        parser.error("arms must be a nonempty unique list of known information arms")
    alphas, seeds = specification["alphas"], specification["seeds"]
    if not alphas or not seeds or len(alphas) != len(set(alphas)) or len(seeds) != len(set(seeds)):
        parser.error("Nonempty, unique alpha and seed lists are required")
    if any(isinstance(s, bool) or not isinstance(s, int) or s < 0 for s in seeds):
        parser.error("Seeds must be nonnegative integers")
    if args.output.exists() and any(args.output.iterdir()):
        parser.error("Output directory is not empty; choose a new directory to preserve earlier results")
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "trajectories").mkdir(exist_ok=True)
    (args.output / "events").mkdir(exist_ok=True)
    jobs = []
    for ai, alpha in enumerate(alphas):
        for seed in seeds:
            regimes = (base.active_arm,) if base.government_policy == "none" else arms
            for regime in regimes:
                cfg = replace(base, alpha=alpha, active_arm=regime)
                run_id = f"alpha{ai:03d}_seed{seed}_{regime}"
                jobs.append((cfg, seed, str(args.output), run_id, specification.get("save_trajectories", True)))
    source_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob("*.py"))}
    snapshot = args.output / "source_snapshot" / "abm_jasss"
    snapshot.mkdir(parents=True, exist_ok=True)
    for name in source_hashes:
        shutil.copyfile(Path(__file__).parent / name, snapshot / name)
    (args.output / "resolved_design.json").write_text(json.dumps([
        {"run_id": j[3], "seed": j[1], "model": j[0].__dict__} for j in jobs], indent=2), encoding="utf-8")
    manifest = {"status": "running", "started_utc": datetime.now(timezone.utc).isoformat(),
                "model_version": __version__, "python": sys.version, "numpy": np.__version__,
                "platform": platform.platform(), "workers": args.workers, "source_sha256": source_hashes,
                "historical_source_review": {
                    "repository": "https://github.com/ldk2645/paper",
                    "reviewed_utc": "2026-09-24",
                    "frozen_v1_model_sha256": "AB78E6C64AFB6FD487E40A48FBBCD1B09A84EE3FBC9085530F8833DE3543D7EC",
                    "relationship": "historical mechanism and evidence reference; not a replication or calibration target",
                    "reference_components": ["threshold-triggered delayed response", "response-strategy contrasts",
                                            "storm-episode records", "source-separated content", "frozen outputs and provenance"]},
                "specification": specification, "planned_world_runs": len(jobs),
                "study_scope": specification.get("study_scope", "exploratory development"),
                "governance": {"policy": base.government_policy, "active_arms": arms,
                               "agenda_is_public_preference": False, "algorithm_transparency_test_implemented": False},
                "analysis": {"bootstrap_draws": 2000, "analysis_seed": 90210, "unit": "independent seed/world",
                             "governance_analysis_seed": 90211,
                             "intervals": "pointwise, percentile; not simultaneous", "paired": True},
                "interpretation": "Synthetic exploratory model outputs; not legacy replication or empirical validation"}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    successes, failures = [], []
    started = time.perf_counter()
    def collect(job, action):
        try:
            result = action()
            successes.append(result)
            (args.output / f'{result["run_id"]}.json').write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(f'{len(successes)+len(failures)}/{len(jobs)} {job[3]} {result["seconds"]:.2f}s', flush=True)
        except Exception:
            failures.append({"run_id": job[3], "traceback": traceback.format_exc()})
            (args.output / "failures.json").write_text(json.dumps(failures, indent=2), encoding="utf-8")
            print(f"FAILED {job[3]}", file=sys.stderr, flush=True)
    if args.workers == 1:
        for job in jobs:
            collect(job, lambda job=job: task(*job))
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(task, *job): job for job in jobs}
            for future in as_completed(futures):
                collect(futures[future], future.result)
    rows = [row for result in sorted(successes, key=lambda r: r["run_id"]) for row in result["summary"]]
    write_csv(args.output / "runs.csv", rows)
    manifest.update(status="failed" if failures else "complete", finished_utc=datetime.now(timezone.utc).isoformat(),
                    elapsed_seconds=time.perf_counter() - started, successful_world_runs=len(successes), failed_world_runs=len(failures))
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    # Failed designs are preserved but never silently summarized as complete experiments.
    if failures:
        raise SystemExit("Some runs failed; inspect failures.json. No aggregate inference was generated.")
    grouped, contrasts = aggregate(rows)
    write_csv(args.output / "aggregate.csv", grouped)
    write_csv(args.output / "paired_contrasts.csv", contrasts)
    write_csv(args.output / "governance_metrics.csv", aggregate_governance(rows))
    svg_plot(args.output / "inference_error.svg", grouped)
    report = ["# Synthetic pilot report", "", "Exploratory simulation only. No real-world or phase-transition claims.", "",
              f"Completed world runs: {len(successes)}; elapsed seconds: {manifest['elapsed_seconds']:.2f}.",
              "", "Negative paired differences mean less inference error than the platform estimator.", "",
              "| alpha | contrast | pairs | mean difference | pointwise 95% interval |", "|---|---|---|---|---|"]
    for r in contrasts:
        interval = "not estimable" if r["ci_low"] is None else f'[{r["ci_low"]:.4f}, {r["ci_high"]:.4f}]'
        report.append(f'| {r["alpha"]} | {r["contrast"]} | {r["n_pairs"]} | {r["mean_difference"]:.4f} | {interval} |')
    report.extend(["", "Oracle zero error follows from its definition; it is not a substantive finding.",
                   "A final observation window is not evidence of convergence. See late_window_shift in runs.csv.",
                   "No-feedback estimates share the same world; feedback comparisons use separate active-arm worlds.",
                   "A full-population platform signal and a smaller survey are not a matched-sample comparison."])
    if base.government_policy == "respond":
        report.extend(["", "The restored reverse-black-box model includes threshold-triggered, delayed responses,",
                       "a fixed governmental agenda, and optional trust feedback. See governance_metrics.csv for",
                       "agenda, attention-preference, response and trust outcomes; inference error alone is not the primary story.",
                       "Event files distinguish scheduling, execution, immediate imposed heat changes and reply publication.",
                       "Government agenda shortfall is not public welfare. Oracle preferences do not reveal ranking rules.",
                       "The exposure-based trust rule contains an assumed off-agenda penalty; test alternative rules.",
                       "Storm episodes ending at the horizon are right-censored; they do not establish irreversibility."])
    (args.output / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
