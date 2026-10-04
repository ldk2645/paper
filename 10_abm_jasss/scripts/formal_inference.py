"""Frozen mother-world inference for the 102 registered formal comparisons.

The estimator is the mean parent-level contrast on that contrast's joint
support. It is not an unconditional mean over undefined outcomes. Pointwise
Student t intervals and tests are exact for independent normal contrasts;
otherwise they are large-sample approximations, including after Holm correction.
The minimum of 30 valid parents is a reporting rule, not a normality guarantee.
Sample SD <= 1e-12 is treated as numerically degenerate: descriptions remain,
but CI and p are withheld. This is a numerical tolerance, not an effect cutoff.
No outcome, significance, missingness, or achieved precision authorizes more runs.

References: NIST's confidence limits and paired t-test documentation,
https://www.itl.nist.gov/div898/handbook/eda/section3/eda352.htm and
https://www.itl.nist.gov/div898/software/dataplot/refman1/auxillar/t_test.htm ;
R's stats::p.adjust documentation for Holm under arbitrary dependence,
https://stat.ethz.ch/R-manual/R-devel/library/stats/html/p.adjust.html .
"""
from collections.abc import Mapping
from copy import deepcopy
from functools import lru_cache
import math
from numbers import Integral, Real
from pathlib import Path
import statistics
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from abm_jasss.research_outcomes import paired_contrast
from scripts.run_precision_pilot import CONTRASTS, PRIMARY

PRIMARY_METRICS = tuple(PRIMARY)
REGISTERED_CONTRASTS = deepcopy(CONTRASTS)
EXPECTED_INFERENCE = {
    "schema": "formal-inference-policy-1",
    "analysis_unit": "mother_world",
    "estimand": "mean_paired_contrast_conditional_on_joint_support",
    "confidence_method": "student_t_pointwise",
    "confidence_level": 0.95,
    "test": "student_t_two_sided_mean_zero",
    "multiplicity_method": "holm",
    "multiplicity_family": "all_102_registered_comparisons",
    "family_size": 102,
    "familywise_alpha": 0.05,
    "min_joint_valid": 30,
    "unavailable_p_for_holm": 1.0,
    "zero_variance": "withhold_interval_and_p",
    "sample_sd_numerical_tolerance": 1e-12,
    "operational_gaps": "withhold_inference_for_affected_family_alpha",
    "target_half_width": 0.02,
    "additional_sampling": False,
}
INFERENCE_POLICY = EXPECTED_INFERENCE
INFERENCE_SPEC = EXPECTED_INFERENCE


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _finite(value, name):
    _require(isinstance(value, Real) and not isinstance(value, bool),
             f"{name} must be finite numeric")
    value = float(value)
    _require(math.isfinite(value), f"{name} must be finite numeric")
    return value


def _parent(value):
    _require(isinstance(value, (str, Integral)) and not isinstance(value, bool)
             and str(value), "parent_id must be a nonempty string or integer")
    return str(value)


def _beta_fraction(a, b, x):
    """Modified Lentz continued fraction for the incomplete beta integral."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) >= tiny else math.copysign(tiny, d))
    fraction = d
    for m in range(1, 10001):
        aa = m * (b - m) * x / ((qam + 2 * m) * (a + 2 * m))
        d, c = 1 + aa * d, 1 + aa / c
        d = 1 / (d if abs(d) >= tiny else math.copysign(tiny, d))
        c = c if abs(c) >= tiny else math.copysign(tiny, c)
        fraction *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + 2 * m) * (qap + 2 * m))
        d, c = 1 + aa * d, 1 + aa / c
        d = 1 / (d if abs(d) >= tiny else math.copysign(tiny, d))
        c = c if abs(c) >= tiny else math.copysign(tiny, c)
        delta = d * c
        fraction *= delta
        if abs(delta - 1) <= 3e-14:
            return fraction
    raise ArithmeticError("Incomplete beta continued fraction did not converge")


def _regularized_beta(x, a, b, *, log_x=None):
    if x <= 0:
        # x itself can underflow while x**a remains representable (e.g. df=1).
        if log_x is None:
            return 0.0
        return math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                        + a * log_x) / a
    if x >= 1:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                     + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1) / (a + b + 2):
        value = front * _beta_fraction(a, b, x) / a
    else:
        value = 1 - front * _beta_fraction(b, a, 1 - x) / b
    return min(1.0, max(0.0, value))


def student_t_two_sided_p(t_statistic, degrees_of_freedom):
    """Return P(|T_df| >= |t|), using the incomplete beta identity.

    Extremely small tails are conservatively floored at the smallest normal
    positive float. No mathematically positive p-value is printed as zero.
    """
    statistic = abs(_finite(t_statistic, "t_statistic"))
    _require(type(degrees_of_freedom) is int and degrees_of_freedom > 0,
             "degrees_of_freedom must be a positive integer")
    df = degrees_of_freedom
    if statistic == 0:
        return 1.0
    ratio = statistic / math.sqrt(df)
    if statistic <= 1:
        # Complement avoids losing small nonzero statistics to x rounding to 1.
        y = ratio * ratio / (1 + ratio * ratio)
        probability = 1 - _regularized_beta(y, .5, df / 2.0)
    else:
        log_x = -2 * math.log(math.hypot(1., ratio))
        probability = _regularized_beta(math.exp(log_x), df / 2.0, .5, log_x=log_x)
    return max(sys.float_info.min, probability)


@lru_cache(maxsize=2048)
def student_t_critical(degrees_of_freedom):
    """The 0.975 t quantile for the frozen pointwise 95% interval."""
    _require(type(degrees_of_freedom) is int and degrees_of_freedom > 0,
             "degrees_of_freedom must be a positive integer")
    lower, upper = 0.0, 2.0
    while student_t_two_sided_p(upper, degrees_of_freedom) > .05:
        upper *= 2
    for _ in range(80):
        middle = (lower + upper) / 2
        if student_t_two_sided_p(middle, degrees_of_freedom) > .05:
            lower = middle
        else:
            upper = middle
    return (lower + upper) / 2


def holm_adjust(p_values):
    """Holm adjustment in input order; None occupies a test with p=1.

    The public helper allows small worked examples. Formal analysis below
    always supplies the entire frozen family of exactly 102 comparisons.
    """
    values = [1.0 if p is None else _finite(p, "p_value") for p in p_values]
    _require(all(0 <= p <= 1 for p in values), "p values must be in [0, 1]")
    adjusted, running = [None] * len(values), 0.0
    for rank, index in enumerate(sorted(range(len(values)), key=values.__getitem__)):
        running = min(1.0, max(running, (len(values) - rank) * values[index]))
        adjusted[index] = running
    return adjusted


def paired_t_inference(values, *, operationally_complete=True):
    """Descriptive mean and frozen t inference for independent paired values."""
    _require(type(operationally_complete) is bool, "operationally_complete must be boolean")
    values = [None if v is None else _finite(v, "paired value") for v in values]
    observed = [v for v in values if v is not None]
    n = len(observed)
    mean = statistics.mean(observed) if n else None
    sd = statistics.stdev(observed) if n >= 2 else None
    se = sd / math.sqrt(n) if sd is not None else None
    status = ("operationally_incomplete" if not operationally_complete else
              "insufficient_joint_support" if n < 30 else
              "degenerate_sample_variance" if sd <= 1e-12 else "estimated")
    result = {
        "status": status, "n_total": len(values), "n_joint_valid": n,
        "mean": mean, "sample_sd": sd, "standard_error": se,
        "degrees_of_freedom": n - 1 if n >= 2 else None,
        "confidence_interval": None, "confidence_half_width": None,
        "confidence_method": "student_t_pointwise_95",
        "t_statistic": None, "p_value_two_sided": None,
        "p_value_for_holm": 1.0, "p_value_numerical_floor": False,
        "observed_target_half_width_met": None, "additional_sampling": False,
    }
    if status != "estimated":
        return result
    statistic = mean / se
    half_width = student_t_critical(n - 1) * se
    # Arithmetic overflow is conservatively handled as an unavailable test.
    if not math.isfinite(statistic) or not math.isfinite(half_width):
        result["status"] = "numerically_unestimable"
        return result
    p_value = student_t_two_sided_p(statistic, n - 1)
    result.update({
        "confidence_interval": [mean - half_width, mean + half_width],
        "confidence_half_width": half_width, "t_statistic": statistic,
        "p_value_two_sided": p_value, "p_value_for_holm": p_value,
        "p_value_numerical_floor": p_value == sys.float_info.min,
        "observed_target_half_width_met": half_width <= .02,
    })
    return result


def validate_inference_spec(spec):
    """Validate the full fixed registry; return canonical parent IDs by alpha."""
    _require(isinstance(spec, Mapping), "inference spec must be a mapping")
    _require(set(spec) == {"alphas", "parent_ids_by_alpha", "metrics", "contrasts", "inference"},
             "Unknown/missing formal inference specification fields")
    _require(spec["alphas"] == [.25, .75], "Formal alpha strata must be [.25, .75]")
    _require(spec["metrics"] == list(PRIMARY_METRICS), "The three primary metrics are fixed")
    _require(spec["contrasts"] == REGISTERED_CONTRASTS, "The 17 registered contrasts are fixed")
    _require(spec["inference"] == EXPECTED_INFERENCE, "The formal inference policy is fixed")
    registry = spec["parent_ids_by_alpha"]
    _require(isinstance(registry, Mapping) and set(registry) == {"0.25", "0.75"},
             "A complete parent registry is required for both alpha strata")
    parents = {}
    for alpha in spec["alphas"]:
        raw = registry[str(alpha)]
        _require(isinstance(raw, (list, tuple)), "Parent registries must be ordered sequences")
        ids = [_parent(value) for value in raw]
        _require(ids and len(ids) == len(set(ids)), "Parent IDs must be nonempty and unique")
        parents[alpha] = ids
    return parents


def build_formal_inference(records, spec):
    """Analyze registered formal records without sampling, resampling or I/O.

    Record shape follows precision_statistics. Parent registry is stratified:
    spec['parent_ids_by_alpha'] = {'0.25': [...], '0.75': [...]}.
    Missing/failed records are operational gaps, distinct from a completed
    world with an undefined metric (None). A family/alpha containing any such
    operational gap retains descriptions but withholds its CI and test.
    """
    parents = validate_inference_spec(spec)
    parent_sets = {alpha: set(ids) for alpha, ids in parents.items()}
    arms = {family: sorted({arm for coefficients in contrasts.values() for arm in coefficients})
            for family, contrasts in REGISTERED_CONTRASTS.items()}
    indexed = {}
    for record in records:
        _require(isinstance(record, Mapping), "Each record must be a mapping")
        family, arm = record["family"], record["arm"]
        alpha, parent = _finite(record["alpha"], "alpha"), _parent(record["parent_id"])
        _require(family in arms, f"Unregistered family: {family}")
        _require(alpha in parents, f"Unregistered alpha: {alpha}")
        _require(parent in parent_sets[alpha], f"Unregistered mother world: {parent}")
        _require(arm in arms[family], f"Unregistered arm for {family}: {arm}")
        key = family, alpha, parent, arm
        _require(key not in indexed, f"Duplicate mother-world arm: {key}")
        status = record.get("status", "complete")
        _require(status in ("complete", "failed"), "record status must be complete or failed")
        metrics = record.get("metrics", {})
        _require(isinstance(metrics, Mapping), "metrics must be a mapping")
        _require(status != "complete" or all(metric in metrics for metric in PRIMARY_METRICS),
                 f"Completed record is missing a registered metric: {key}")
        normalized = {}
        for metric in PRIMARY_METRICS:
            value = metrics.get(metric)
            _require(status != "failed" or value is None, "Failed records cannot contribute metrics")
            value = None if value is None else _finite(value, metric)
            _require(value is None or 0 <= value <= 1, f"{metric} must be in [0, 1] or None")
            normalized[metric] = value
        indexed[key] = {"status": status, "metrics": normalized}

    groups, all_items = [], []
    for family, contrasts in REGISTERED_CONTRASTS.items():
        for alpha, ids in parents.items():
            missing, failed = [], []
            by_metric = {metric: {parent: {} for parent in ids} for metric in PRIMARY_METRICS}
            for parent in ids:
                for arm in arms[family]:
                    item = indexed.get((family, alpha, parent, arm))
                    identity = {"parent_id": parent, "arm": arm}
                    if item is None:
                        missing.append(identity)
                    elif item["status"] == "failed":
                        failed.append(identity)
                    for metric in PRIMARY_METRICS:
                        by_metric[metric][parent][arm] = item["metrics"][metric] if item else None
            complete = not missing and not failed
            group = {"family": family, "alpha": alpha, "n_parent_worlds": len(ids),
                     "arm_order": arms[family], "missing_records": missing,
                     "failed_records": failed, "operationally_complete": complete, "contrasts": {}}
            for name, coefficients in contrasts.items():
                group["contrasts"][name] = {}
                for metric in PRIMARY_METRICS:
                    paired = paired_contrast(by_metric[metric], coefficients)
                    paired.pop("normal95_interval")
                    paired.pop("interval_method")
                    estimate = paired_t_inference(paired["paired_values"].values(),
                                                  operationally_complete=complete)
                    item = {**paired, **estimate,
                            "comparison_id": f"{family}/alpha={alpha}/{name}/{metric}",
                            "estimand": EXPECTED_INFERENCE["estimand"]}
                    group["contrasts"][name][metric] = item
                    all_items.append(item)
            groups.append(group)
    _require(len(all_items) == 102, "The full Holm family must contain exactly 102 comparisons")
    adjusted = holm_adjust(item["p_value_for_holm"] for item in all_items)
    for item, adjusted_p in zip(all_items, adjusted):
        item["p_value_holm"] = adjusted_p
        item["reject_holm_0_05"] = item["status"] == "estimated" and adjusted_p <= .05
    return {
        "schema": "formal-inference-1", "inference": deepcopy(EXPECTED_INFERENCE),
        "parent_ids_by_alpha": {str(alpha): ids for alpha, ids in parents.items()},
        "groups": groups, "comparison_count": len(all_items),
        "operationally_complete": all(group["operationally_complete"] for group in groups),
        "additional_sampling": False,
        "interpretation": (
            "Conditional on contrast-specific joint support; independent mother worlds. "
            "Pointwise t intervals are not simultaneous intervals. Normal contrasts give exact "
            "marginal tests; otherwise t inference and Holm familywise control are approximations. "
            "Thirty valid parents do not guarantee accurate approximation. No adaptive sampling."),
    }
