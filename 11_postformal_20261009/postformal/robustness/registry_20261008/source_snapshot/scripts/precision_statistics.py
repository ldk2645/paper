"""Independent-pilot precision planning from one summary per mother-world arm.

``build_precision_analysis(records, spec)`` accepts records with ``family``,
``alpha``, ``parent_id``, ``arm``, ``status`` (complete/failed), and ``metrics``.
The spec contains ``alphas``, the ordered, complete ``parent_ids`` registry,
and ``contrasts = {family: {contrast_name: {arm: coefficient}}}``. Optional
``metrics`` selects registered primary outcomes; planning defaults are h=.02,
min_valid=30, max_total=1000. Missing arms and failed runs remain in the parent
denominator, separately flagged as operational gaps that prevent planning
acceptance. A completed world's metric may legitimately be None.

No ticks, agents, arms, or alpha strata become extra independent replications.
The frozen engine's paired_contrast and precision_plan supply the calculations.
Outputs are planning approximations, never formal inference or release approval.
"""
from collections.abc import Mapping
import math
from numbers import Integral, Real
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from abm_jasss.research_outcomes import paired_contrast, precision_plan


PRIMARY_METRICS = (
    "platform_representation_gap", "perception_error", "targeting_error_trigger",
)


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _finite(value, name):
    _require(isinstance(value, Real) and not isinstance(value, bool),
             f"{name} must be a finite number")
    value = float(value)
    _require(math.isfinite(value), f"{name} must be a finite number")
    return value


def _parent(value):
    _require(isinstance(value, (str, Integral)) and not isinstance(value, bool)
             and str(value) != "", "parent_id must be a nonempty string or integer")
    return str(value)


def _unique(values, name):
    _require(values and len(values) == len(set(values)),
             f"{name} must be nonempty and unique")


def _wilson_upper(n, valid):
    if not n:
        return None
    z = 1.96
    probability = valid / n
    center = probability + z * z / (2 * n)
    radius = z * math.sqrt(probability * (1 - probability) / n
                           + z * z / (4 * n * n))
    return min(1.0, (center + radius) / (1 + z * z / n))


def _shared_plan(entries, max_total, operationally_complete):
    """Take a maximum across requirements, never across observed effects."""
    entries = list(entries)
    unplannable = [name for name, item in entries
                  if item["required_total_uncapped"] is None]
    required = [item["required_total_uncapped"] for _, item in entries
                if item["required_total_uncapped"] is not None]
    partial_max = max(required) if required else None
    total = partial_max if not unplannable else None
    fixed = min(total, max_total) if total is not None else None
    feasible = (operationally_complete and total is not None and total <= max_total)
    limiting = [name for name, item in entries
                if partial_max is not None and item["required_total_uncapped"] == partial_max]
    return {
        "required_total_uncapped": total,
        "fixed_total": fixed,
        "max_estimable_required_total": partial_max,
        "max_total": max_total,
        "unplannable_items": unplannable,
        "limiting_items": limiting,
        "operationally_complete": operationally_complete,
        "precision_target_feasible": feasible,
        "budget_capped": total is not None and total > max_total,
        "status": ("incomplete_pilot" if not operationally_complete else
                   "insufficient_pilot_variance" if unplannable else
                   "budget_limited" if not feasible else "planned"),
        "formal_ready": False,
    }


def build_precision_analysis(records, spec):
    """Build all registered contrasts, retaining the entire mother registry.

    One shared future n is returned per family/alpha and also per alpha across
    all families. Undefined requirements make the shared plan undefined rather
    than silently dropping that contrast. Capped requirements retain their
    uncapped n and report that the precision target is not feasible.
    """
    _require(isinstance(spec, Mapping), "spec must be a mapping")
    parents = [_parent(value) for value in spec["parent_ids"]]
    _unique(parents, "parent_ids after string conversion")
    alphas = [_finite(value, "alpha") for value in spec["alphas"]]
    _unique(alphas, "alphas")
    _require(all(0 <= value <= 1 for value in alphas), "alpha must be in [0, 1]")
    metrics = list(spec.get("metrics", PRIMARY_METRICS))
    _unique(metrics, "metrics")
    _require(set(metrics) <= set(PRIMARY_METRICS), "Only registered primary metrics are supported")
    contrasts = spec["contrasts"]
    _require(isinstance(contrasts, Mapping) and contrasts, "contrasts must be a nonempty mapping")
    settings = {key: spec.get(key, default) for key, default in (
        ("target_half_width", .02), ("min_valid", 30), ("max_total", 1000))}
    precision_plan([], **settings)  # Validate settings even with an empty pilot.
    arms = {}
    for family, family_contrasts in contrasts.items():
        _require(isinstance(family, str) and family, "family must be a nonempty string")
        _require(isinstance(family_contrasts, Mapping) and family_contrasts,
                 "Each family needs at least one contrast")
        arms[family] = set()
        for name, coefficients in family_contrasts.items():
            _require(isinstance(name, str) and name, "contrast name must be a nonempty string")
            _require(isinstance(coefficients, Mapping), "coefficients must be a mapping")
            _require(all(isinstance(arm, str) and arm for arm in coefficients),
                     "arm must be a nonempty string")
            normalized = paired_contrast({}, coefficients)["coefficients"]
            arms[family].update(normalized)

    indexed = {}
    for record in records:
        _require(isinstance(record, Mapping), "Each record must be a mapping")
        family, arm = record["family"], record["arm"]
        alpha, parent = _finite(record["alpha"], "alpha"), _parent(record["parent_id"])
        _require(family in contrasts, f"Unregistered family: {family}")
        _require(alpha in alphas, f"Unregistered alpha: {alpha}")
        _require(parent in parents, f"Unregistered mother world: {parent}")
        _require(arm in arms[family], f"Unregistered arm for {family}: {arm}")
        key = family, alpha, parent, arm
        _require(key not in indexed, f"Duplicate mother-world arm: {key}")
        status = record.get("status", "complete")
        _require(status in ("complete", "failed"), "record status must be complete or failed")
        values = record.get("metrics", {})
        _require(isinstance(values, Mapping), "metrics must be a mapping")
        if status == "complete":
            _require(all(metric in values for metric in metrics),
                     f"Completed record is missing a registered metric: {key}")
        normalized = {}
        for metric in metrics:
            value = values.get(metric)
            _require(status != "failed" or value is None,
                     "Failed records cannot contribute measured metrics")
            value = None if value is None else _finite(value, metric)
            _require(value is None or 0 <= value <= 1,
                     f"{metric} must be in [0, 1] or None")
            normalized[metric] = value
        indexed[key] = {"status": status, "metrics": normalized}

    groups = []
    alpha_entries = {alpha: [] for alpha in alphas}
    alpha_complete = {alpha: True for alpha in alphas}
    for family, family_contrasts in contrasts.items():
        for alpha in alphas:
            missing, failed = [], []
            by_metric = {metric: {parent: {} for parent in parents} for metric in metrics}
            for parent in parents:
                for arm in sorted(arms[family]):
                    item = indexed.get((family, alpha, parent, arm))
                    identity = {"parent_id": parent, "arm": arm}
                    if item is None:
                        missing.append(identity)
                    elif item["status"] == "failed":
                        failed.append(identity)
                    for metric in metrics:
                        by_metric[metric][parent][arm] = item["metrics"][metric] if item else None
            operationally_complete = not missing and not failed
            group = {"family": family, "alpha": alpha,
                     "n_parent_worlds": len(parents), "arm_order": sorted(arms[family]),
                     "missing_records": missing, "failed_records": failed, "contrasts": {}}
            entries = []
            for name, coefficients in family_contrasts.items():
                group["contrasts"][name] = {}
                for metric in metrics:
                    paired = paired_contrast(by_metric[metric], coefficients)
                    plan = precision_plan(paired["paired_values"].values(), **settings)
                    sd = paired["sample_sd"]
                    result = {**paired, "sample_variance": sd * sd if sd is not None else None,
                              "joint_support_wilson95": [
                                  plan["joint_support_wilson95_lower"],
                                  _wilson_upper(paired["n_total"], paired["n_joint_valid"])],
                              "precision_plan": plan}
                    group["contrasts"][name][metric] = result
                    entries.append((f"{name}/{metric}", plan))
                    alpha_entries[alpha].append((f"{family}/{name}/{metric}", plan))
            group["shared_plan"] = _shared_plan(entries, settings["max_total"], operationally_complete)
            alpha_complete[alpha] &= operationally_complete
            groups.append(group)
    return {
        "schema": "precision-analysis-1", "analysis_unit": "mother_world",
        "parent_ids": parents, "alphas": alphas, "metrics": metrics,
        "planning_settings": settings, "groups": groups,
        "shared_by_alpha": [{"alpha": alpha, **_shared_plan(
            alpha_entries[alpha], settings["max_total"], alpha_complete[alpha])} for alpha in alphas],
        "formal_ready": False,
        "interpretation": "Independent pilot planning approximation; no finite-sample or simultaneous coverage guarantee.",
    }


def assess_precision_stability(initial_analysis, expanded_analysis, *,
                               variance_relative_tolerance=.25,
                               support_absolute_tolerance=.10):
    """Diagnose the registered first 20 versus all 40 parents per alpha.

    Expansion from 20 to 40 is unconditional; 40 is a fixed pilot stop. This
    function is diagnostic only and never authorizes additional sampling. It
    compares abs(v40-v20)/max(v20,v40) <= .25 and abs(p40-p20) <= .10 by default,
    and requires >= min_valid jointly measurable parents at 40. Inclusive
    thresholds allow only floating-point roundoff (absolute tolerance 1e-12).
    Two zero
    variances are stable; exactly one zero is unstable. Undefined variance is
    unassessable. Means, signs, confidence intervals and p-values are not read.
    """
    variance_tolerance = _finite(variance_relative_tolerance, "variance_relative_tolerance")
    support_tolerance = _finite(support_absolute_tolerance, "support_absolute_tolerance")
    _require(0 <= variance_tolerance <= 1 and 0 <= support_tolerance <= 1,
             "Stability tolerances must be in [0, 1]")
    parents20, parents40 = initial_analysis["parent_ids"], expanded_analysis["parent_ids"]
    _require(len(parents20) == 20 and len(parents40) == 40
             and parents40[:20] == parents20, "Stability requires the registered first 20 and all 40 parents")
    for key in ("alphas", "metrics", "planning_settings"):
        _require(initial_analysis[key] == expanded_analysis[key], f"Pilot {key} changed between stages")
    min_valid = expanded_analysis["planning_settings"]["min_valid"]

    def flatten(analysis):
        flat = {}
        for group in analysis["groups"]:
            for name, outcomes in group["contrasts"].items():
                for metric, item in outcomes.items():
                    key = group["family"], group["alpha"], name, metric
                    _require(key not in flat, "Duplicate analysis item")
                    flat[key] = item
        return flat

    first, second = flatten(initial_analysis), flatten(expanded_analysis)
    _require(first.keys() == second.keys(), "Registered contrasts changed between pilot stages")
    results = []
    for key, old in first.items():
        new = second[key]
        _require(old["coefficients"] == new["coefficients"], "Contrast coefficients changed between stages")
        v20, v40 = old["sample_variance"], new["sample_variance"]
        p20, p40 = old["joint_support"], new["joint_support"]
        ratio = (None if v20 is None or v40 is None else
                 0.0 if max(v20, v40) == 0 else abs(v40 - v20) / max(v20, v40))
        difference = None if p20 is None or p40 is None else abs(p40 - p20)
        variance_stable = ratio is not None and (
            ratio <= variance_tolerance
            or math.isclose(ratio, variance_tolerance, rel_tol=0, abs_tol=1e-12))
        support_stable = difference is not None and (
            difference <= support_tolerance
            or math.isclose(difference, support_tolerance, rel_tol=0, abs_tol=1e-12))
        sufficient = new["n_joint_valid"] >= min_valid
        results.append({
            "family": key[0], "alpha": key[1], "contrast": key[2], "metric": key[3],
            "variance_first20": v20, "variance_all40": v40,
            "variance_relative_change": ratio, "variance_stable": variance_stable,
            "support_first20": p20, "support_all40": p40,
            "support_absolute_change": difference, "support_stable": support_stable,
            "joint_valid_all40": new["n_joint_valid"], "sufficient_joint_valid": sufficient,
            "stable": variance_stable and support_stable and sufficient,
        })
    operationally_complete = all(
        group["shared_plan"]["operationally_complete"]
        for analysis in (initial_analysis, expanded_analysis) for group in analysis["groups"])
    stable = operationally_complete and all(item["stable"] for item in results)
    return {
        "schema": "precision-stability-1", "items": results,
        "variance_relative_tolerance": variance_tolerance,
        "support_absolute_tolerance": support_tolerance, "min_valid": min_valid,
        "operationally_complete": operationally_complete, "all_items_stable": stable,
        "status": "planning_stable" if stable else "planning_unstable",
        "pilot_stop": "fixed_budget_40_per_alpha", "additional_pilot_sampling": False,
        "uses_effect_direction_or_significance": False, "formal_ready": False,
    }
