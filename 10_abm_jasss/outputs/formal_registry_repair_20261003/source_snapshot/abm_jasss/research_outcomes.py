"""Research summaries with explicit support, event cohorts and censoring.

These functions consume evaluator records, never government observations.  A
world is the unit of replication.  Missing measurements are ``None`` and no
function serializes NaN or silently substitutes zero for an unobserved outcome.
"""
from collections import Counter, defaultdict
import math
from numbers import Integral
import statistics


DISTANCE_KEYS = (
    "platform_representation_gap", "perception_error", "exposure_gap",
    "visible_signal_current_gap", "visible_signal_matched_gap",
    "signal_estimate_distance",
)

DEFAULT_CONTRASTS = {
    "pref_given_rule0": {"I10": 1, "I00": -1},
    "pref_given_rule1": {"I11": 1, "I01": -1},
    "rule_given_pref0": {"I01": 1, "I00": -1},
    "rule_given_pref1": {"I11": 1, "I10": -1},
    "interaction": {"I11": 1, "I10": -1, "I01": -1, "I00": 1},
}


def _integer(value, name, minimum=0):
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError(f"{name} must be an integer >= {minimum}")
    result = int(value)
    if result < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return result


def _finite(value, name):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def _distance(value, name):
    if value is None:
        return None
    result = _finite(value, name)
    if not 0 <= result <= 1:
        raise ValueError(f"{name} must be in [0, 1]")
    return result


def _distribution(value, name, n_topics=None, optional=False):
    if value is None and optional:
        return None
    if value is None or isinstance(value, (str, bytes, dict)):
        raise ValueError(f"{name} must be a probability vector")
    try:
        result = [_finite(item, name) for item in value]
    except TypeError as exc:
        raise ValueError(f"{name} must be a probability vector") from exc
    if not result or (n_topics is not None and len(result) != n_topics):
        raise ValueError(f"{name} has an inconsistent topic count")
    if any(item < 0 or item > 1 for item in result) or not math.isclose(sum(result), 1, abs_tol=1e-9):
        raise ValueError(f"{name} must be a probability vector")
    return result


def _tv(left, right):
    return None if left is None or right is None else 0.5 * sum(abs(a - b) for a, b in zip(left, right))


def _mean(values):
    values = list(values)
    return statistics.fmean(values) if values else None


def _same_vector(left, right, name):
    if len(left) != len(right) or any(not math.isclose(a, b, abs_tol=1e-9) for a, b in zip(left, right)):
        raise ValueError(f"{name} disagrees with its referenced preference")


def _observed_metric(row, key, derived=None, derive=False):
    recorded = _distance(row.get(key), key)
    if derive:
        if recorded is not None and (derived is None or not math.isclose(recorded, derived, abs_tol=1e-9)):
            raise ValueError(f"{key} disagrees with its recorded distributions")
        return derived
    return recorded


def summarize_world(trajectory, events, config_dict):
    """Summarize one world using its *configured*, fixed terminal window.

    ``trajectory`` is an ordered sequence of evaluator dictionaries.  It may be
    incomplete: absent ticks remain absent from coverage denominators.  Every
    row requires ``step`` and ``P_true``.  Optional probability vectors are
    ``E_exposure``, ``S_public``, ``S_available`` and ``P_hat_gov``.  The six
    distance fields are checked against vectors when those vectors are supplied.
    ``has_data=False`` excludes a prior estimate from the main perception mean
    and reports it separately.  The signal-coverage threshold applies to main
    outcome 1, not to the exposure mechanism diagnostic.

    ``events`` contains one complete lifecycle record per planned action, with
    stable event_id, topic, trigger_step, due_step, execution_step (None for
    pending), P_trigger and P_execution.  Targeting is equal-weighted across
    (trigger, execution) cohorts executed in the terminal window.  Completion
    uses an independent, inclusive trigger enrollment window and fixed L.
    """
    steps = _integer(config_dict["steps"], "steps", 1)
    final_window = _integer(config_dict.get("final_window", steps), "final_window", 1)
    if final_window > steps:
        raise ValueError("final_window must not exceed steps")
    minimum_coverage = _distance(config_dict.get("min_signal_coverage", 0), "min_signal_coverage")
    if minimum_coverage is None:
        raise ValueError("min_signal_coverage cannot be missing")
    followup = _integer(config_dict.get("completion_followup", 0), "completion_followup")
    completion_start = _integer(config_dict.get("completion_start", 0), "completion_start")
    completion_end = _integer(config_dict.get("completion_end", steps - 1), "completion_end")
    if not completion_start <= completion_end < steps:
        raise ValueError("completion enrollment window must lie within configured steps")
    rows = list(trajectory)
    events = list(events)
    first_window = steps - final_window
    by_step, measured = {}, defaultdict(list)
    priors = []
    n_topics = None
    previous_step = -1
    for row in rows:
        step = _integer(row["step"], "step")
        if step <= previous_step or step >= steps:
            raise ValueError("Trajectory steps must be ordered, unique and within configured steps")
        previous_step = step
        p = _distribution(row.get("P_true"), "P_true", n_topics)
        n_topics = len(p)
        by_step[step] = p
        vectors = {key: _distribution(row.get(key), key, n_topics, optional=True)
                   for key in ("E_exposure", "S_public", "S_available", "P_hat_gov")}
        has_data = row.get("has_data", True)
        if not isinstance(has_data, bool):
            raise ValueError("has_data must be boolean")
        derived = {
            "platform_representation_gap": ("S_public", _tv(p, vectors["S_public"])),
            "perception_error": ("P_hat_gov", _tv(p, vectors["P_hat_gov"])),
            "exposure_gap": ("E_exposure", _tv(p, vectors["E_exposure"])),
            "visible_signal_current_gap": ("S_available", _tv(p, vectors["S_available"])),
        }
        for key in DISTANCE_KEYS:
            vector_key, value = derived.get(key, (None, None))
            value = _observed_metric(row, key, value, vector_key in row if vector_key else False)
            if step < first_window or value is None:
                continue
            if key == "perception_error" and not has_data:
                priors.append(value)
            else:
                measured[key].append(value)
    observed_end = previous_step
    if n_topics is None and events:
        n_topics = len(_distribution(events[0].get("P_trigger"), "P_trigger"))
    metric_coverage = {}
    summary = {}
    for key in DISTANCE_KEYS:
        valid = len(measured[key])
        coverage = valid / final_window
        mean_valid = _mean(measured[key])
        eligible = valid > 0 and (key != "platform_representation_gap" or coverage >= minimum_coverage)
        summary[key] = mean_valid if eligible else None
        metric_coverage[key] = {
            "valid_ticks": valid, "expected_ticks": final_window,
            "coverage": coverage, "missing_fraction": 1 - coverage,
            "mean_valid_ticks": mean_valid, "measurable": eligible,
        }
    summary.update({
        "evaluation_start": first_window, "evaluation_end": steps - 1,
        "observed_end": observed_end if rows else None,
        "observed_window_ticks": sum(step >= first_window for step in by_step),
        "metric_coverage": metric_coverage,
        "prior_perception_error": _mean(priors), "prior_estimate_ticks": len(priors),
    })

    grouped = defaultdict(list)
    pending = []
    event_ids = set()
    parsed = []
    for event in events:
        event_id = event.get("event_id")
        if not isinstance(event_id, (str, Integral)) or isinstance(event_id, bool) or str(event_id) == "":
            raise ValueError("Each action requires a nonempty stable event_id")
        event_id = str(event_id)
        if event_id in event_ids:
            raise ValueError("Duplicate action event_id")
        event_ids.add(event_id)
        topic = _integer(event["topic"], "topic")
        trigger = _integer(event["trigger_step"], "trigger_step")
        due = _integer(event["due_step"], "due_step")
        execution = event.get("execution_step")
        execution = None if execution is None else _integer(execution, "execution_step")
        if topic >= n_topics or trigger > observed_end or due < trigger:
            raise ValueError("Action topic or trigger/due references are invalid")
        if execution is not None and (execution < due or execution > observed_end):
            raise ValueError("Execution must be at/after due and within the observed horizon")
        p_trigger = _distribution(event.get("P_trigger"), "P_trigger", n_topics)
        if trigger in by_step:
            _same_vector(p_trigger, by_step[trigger], "P_trigger")
        p_execution = _distribution(event.get("P_execution"), "P_execution", n_topics, optional=execution is None)
        if execution is None and p_execution is not None:
            raise ValueError("A pending action must not contain P_execution")
        if execution in by_step:
            _same_vector(p_execution, by_step[execution], "P_execution")
        item = {"event_id": event_id, "topic": topic, "trigger_step": trigger,
                "due_step": due, "execution_step": execution,
                "P_trigger": p_trigger, "P_execution": p_execution}
        parsed.append(item)
        if execution is None:
            pending.append({"event_id": event_id, "topic": topic, "trigger_step": trigger,
                            "due_step": due, "right_censored": True,
                            "censor_wait": observed_end - trigger,
                            "due_status": "not_yet_due" if due > observed_end else "overdue"})
        elif execution >= first_window:
            grouped[(trigger, execution)].append(item)

    cohorts = []
    for (trigger, execution), group in sorted(grouped.items()):
        p_trigger, p_execution = group[0]["P_trigger"], group[0]["P_execution"]
        for item in group[1:]:
            _same_vector(item["P_trigger"], p_trigger, "Within-cohort P_trigger")
            _same_vector(item["P_execution"], p_execution, "Within-cohort P_execution")
        counts = Counter(item["topic"] for item in group)
        response = [counts[k] / len(group) for k in range(n_topics)]
        at_trigger, at_execution = _tv(response, p_trigger), _tv(response, p_execution)
        cohorts.append({
            "trigger_step": trigger, "execution_step": execution,
            "due_steps": sorted({item["due_step"] for item in group}),
            "event_ids": [item["event_id"] for item in group], "n_actions": len(group),
            "target_distribution": response, "P_trigger": p_trigger, "P_execution": p_execution,
            "targeting_error_trigger": at_trigger, "targeting_error_execution": at_execution,
            "signed_targeting_change": at_execution - at_trigger,
            "preference_shift_during_wait": _tv(p_trigger, p_execution),
            "waiting_time": execution - trigger,
        })
    executed = [item for item in parsed if item["execution_step"] is not None]
    window_executed = [item for item in executed if item["execution_step"] >= first_window]
    summary.update({
        "targeting_error_trigger": _mean(row["targeting_error_trigger"] for row in cohorts),
        "targeting_error_execution": _mean(row["targeting_error_execution"] for row in cohorts),
        "signed_targeting_change": _mean(row["signed_targeting_change"] for row in cohorts),
        "execution_count": len(window_executed), "execution_count_total": len(executed),
        "execution_coverage": len({item["execution_step"] for item in window_executed}) / final_window,
        "has_response": bool(window_executed), "executed_cohort_count": len(cohorts),
        "scheduled_count": sum(item["trigger_step"] >= first_window for item in parsed),
        "scheduled_count_total": len(parsed), "pending_count": len(pending),
        "waiting_time": _mean(item["execution_step"] - item["trigger_step"] for item in window_executed),
        "executed_cohorts": cohorts, "pending_events": pending,
    })
    enrolled = [item for item in parsed if completion_start <= item["trigger_step"] <= completion_end]
    complete = incomplete = unknown = not_yet_due = overdue = 0
    completion_events = []
    for item in enrolled:
        execution = item["execution_step"]
        deadline = item["trigger_step"] + followup
        if execution is not None and execution <= deadline:
            state = "completed_within_L"
            complete += 1
        elif observed_end >= deadline:
            state = "not_completed_within_L"
            incomplete += 1
        else:
            state = "unknown_right_censored"
            unknown += 1
        if execution is None:
            not_yet_due += item["due_step"] > observed_end
            overdue += item["due_step"] <= observed_end
        completion_events.append({"event_id": item["event_id"], "deadline": deadline, "status": state})
    enrollment_complete = observed_end >= completion_end
    denominator = len(enrolled)
    rate = complete / denominator if denominator and not unknown and enrollment_complete else None
    status = ("incomplete_enrollment" if not enrollment_complete else "empty_cohort" if not denominator
              else "right_censored" if unknown else "fully_ascertained")
    summary["response_completion_L"] = rate
    summary["completion"] = {
        "trigger_start": completion_start, "trigger_end": completion_end,
        "followup_L": followup, "enrollment_complete": enrollment_complete,
        "planned_followup_end": completion_end + followup, "observed_end": summary["observed_end"],
        "n_enrolled": denominator, "completed_within_L": complete,
        "not_completed_within_L": incomplete, "unknown_right_censored": unknown,
        "pending_not_yet_due": not_yet_due, "pending_overdue": overdue,
        "rate": rate, "status": status,
        "lower_bound": complete / denominator if denominator and enrollment_complete else None,
        "upper_bound": (complete + unknown) / denominator if denominator and enrollment_complete else None,
        "events": completion_events,
    }
    return summary


def recovery_diagnostic(rows, key, reference, tolerance, window, consecutive, start_step):
    """Detect sustained recovery relative to an externally supplied healthy mean.

    ``reference=None`` explicitly means that recovery cannot be identified.
    Rolling windows include the current tick and require every consecutive tick
    to be observed.  Initial health is assessed at start_step; if that window is
    missing, recovery status is unknown rather than inferred from later health.
    A recovery time is the confirmation tick minus start_step (the onset is
    also saved).  Rebounds are counted separately and never erase a first event.
    """
    window = _integer(window, "window", 1)
    consecutive = _integer(consecutive, "consecutive", 1)
    start_step = _integer(start_step, "start_step")
    tolerance = _finite(tolerance, "tolerance")
    if tolerance < 0:
        raise ValueError("tolerance must be nonnegative")
    reference = None if reference is None else _finite(reference, "reference")
    by_step = {}
    previous = -1
    for row in rows:
        step = _integer(row["step"], "step")
        if step <= previous:
            raise ValueError("Recovery rows must be ordered and unique")
        previous = step
        value = row.get(key)
        by_step[step] = None if value is None else _finite(value, key)
    end = max(by_step, default=start_step - 1)
    rolling = []
    for step in range(start_step, end + 1):
        values = [by_step.get(tick) for tick in range(step - window + 1, step + 1)]
        value = _mean(values) if all(item is not None for item in values) else None
        rolling.append({"step": step, "value": value})
    first = rolling[0]["value"] if rolling else None
    last = rolling[-1]["value"] if rolling else None
    result = {
        "key": key, "healthy_reference": reference, "tolerance": tolerance,
        "window": window, "consecutive": consecutive, "start_step": start_step,
        "observed_end": end if end >= start_step else None,
        "initial_rolling_mean": first, "terminal_rolling_mean": last,
        "improvement_from_start": first - last if first is not None and last is not None else None,
        "recovery_time": None, "recovery_onset_step": None, "recovery_confirmed_step": None,
        "right_censored": False, "censor_time": None, "rebound_count": 0,
        "cumulative_excess": None, "valid_post_start_ticks": sum(value is not None for step, value in by_step.items() if step >= start_step),
        "rolling": rolling,
    }
    if reference is None:
        result["status"] = "no_health_reference"
        return result
    threshold = reference + tolerance
    result["threshold"] = threshold
    valid = [value for step, value in by_step.items() if step >= start_step and value is not None]
    result["cumulative_excess"] = sum(max(0, value - threshold) for value in valid) if valid else None
    if first is None:
        result["status"] = "initial_state_unobserved"
        return result
    already_healthy = first <= threshold
    if already_healthy:
        result["status"] = "not_required"
    else:
        streak = 0
        for item in rolling:
            streak = streak + 1 if item["value"] is not None and item["value"] <= threshold else 0
            if streak >= consecutive:
                result.update({"status": "recovered", "recovery_time": item["step"] - start_step,
                               "recovery_onset_step": item["step"] - consecutive + 1,
                               "recovery_confirmed_step": item["step"]})
                break
        else:
            result.update({"status": "right_censored", "right_censored": True,
                           "censor_time": max(0, end - start_step)})
    if already_healthy or result.get("status") == "recovered":
        after = start_step if already_healthy else result["recovery_confirmed_step"]
        previous_healthy = True
        for item in rolling:
            if item["step"] <= after:
                continue
            if item["value"] is None:
                previous_healthy = None
            else:
                healthy = item["value"] <= threshold
                if previous_healthy is True and not healthy:
                    result["rebound_count"] += 1
                previous_healthy = healthy
    return result


def precision_plan(paired_values, target_half_width=.02, min_valid=30, max_total=1000):
    """Plan a *fixed* future total from independent pilot paired differences.

    Include one None per jointly unmeasurable parent world; removing those
    values would inflate the estimated support probability.  Variance uses the
    sample SD (ddof=1).  Total n uses the lower endpoint of a 95% Wilson interval
    for joint support, rather than its point estimate.  This conservative
    support adjustment is a planning heuristic, not a guarantee of coverage.
    """
    target_half_width = _finite(target_half_width, "target_half_width")
    if target_half_width <= 0:
        raise ValueError("target_half_width must be positive")
    min_valid = _integer(min_valid, "min_valid", 2)
    max_total = _integer(max_total, "max_total", 1)
    values = [None if value is None else _finite(value, "paired value") for value in paired_values]
    valid = [value for value in values if value is not None]
    n_total, n_valid = len(values), len(valid)
    probability = n_valid / n_total if n_total else None
    z = 1.96
    lower = None
    if n_total:
        center = probability + z * z / (2 * n_total)
        radius = z * math.sqrt(probability * (1 - probability) / n_total + z * z / (4 * n_total * n_total))
        lower = max(0.0, (center - radius) / (1 + z * z / n_total))
    sd = statistics.stdev(valid) if n_valid >= 2 else None
    required_valid = max(min_valid, math.ceil((z * sd / target_half_width) ** 2)) if sd is not None else None
    required_total = math.ceil(required_valid / lower) if required_valid is not None and lower and lower > 0 else None
    fixed_total = min(max_total, required_total) if required_total is not None else None
    feasible = required_total is not None and required_total <= max_total
    return {
        "pilot_total": n_total, "pilot_joint_valid": n_valid, "pilot_joint_invalid": n_total - n_valid,
        "paired_mean": _mean(valid), "paired_sample_sd": sd,
        "joint_support": probability, "joint_support_wilson95_lower": lower,
        "target_half_width": target_half_width, "min_valid": min_valid, "max_total": max_total,
        "required_valid": required_valid, "required_total_uncapped": required_total,
        "fixed_total": fixed_total, "precision_target_feasible": feasible,
        "budget_capped": required_total is not None and required_total > max_total,
        "expected_valid_at_point_support": fixed_total * probability if fixed_total is not None else None,
        "expected_valid_at_lower_support": fixed_total * lower if fixed_total is not None else None,
        "status": "insufficient_pilot_variance" if sd is None else "budget_limited" if not feasible else "planned",
        "support_method": "Wilson 95% lower endpoint; paired sample SD; z=1.96 planning approximation",
        "formal_stop_rule": "Freeze total before new formal seeds; do not sample until min_valid is reached.",
        "formal_ready": False,
    }


def paired_contrast(world_metric_by_parent, coefficients=None):
    """Calculate parent-level linear contrasts only on their joint support.

    Input is ``{parent_id: {cell_id: value_or_None}}``.  Missing cells count as
    unmeasurable.  Without coefficients, return all five preregistered 2x2
    contrasts.  A supplied ``{cell_id: coefficient}`` returns one contrast.
    Each result retains a None for unsupported parents, which can be passed
    directly to precision_plan via ``result['paired_values'].values()``.
    """
    if coefficients is None:
        return {name: paired_contrast(world_metric_by_parent, spec) for name, spec in DEFAULT_CONTRASTS.items()}
    coefficients = {key: _finite(value, "coefficient") for key, value in coefficients.items()}
    coefficients = {key: value for key, value in coefficients.items() if value != 0}
    if not coefficients:
        raise ValueError("At least one nonzero contrast coefficient is required")
    if not math.isclose(sum(coefficients.values()), 0, abs_tol=1e-12):
        raise ValueError("Contrast coefficients must sum to zero")
    patterns = Counter()
    paired = {}
    total = joint = single = none = partial = 0
    for parent, cells in world_metric_by_parent.items():
        if str(parent) in paired:
            raise ValueError("Parent IDs collide after JSON string conversion")
        values = [None if cells.get(key) is None else _finite(cells[key], "cell value") for key in coefficients]
        count = sum(value is not None for value in values)
        patterns["".join("1" if value is not None else "0" for value in values)] += 1
        total += 1
        joint += count == len(values)
        single += count == 1
        none += count == 0
        partial += 0 < count < len(values)
        paired[str(parent)] = sum(coefficient * value for coefficient, value in zip(coefficients.values(), values)) if count == len(values) else None
    values = [value for value in paired.values() if value is not None]
    mean = _mean(values)
    sd = statistics.stdev(values) if len(values) >= 2 else None
    se = sd / math.sqrt(len(values)) if sd is not None else None
    return {
        "coefficients": coefficients, "cell_order": list(coefficients),
        "n_total": total, "n_joint_valid": joint, "n_single_sided_valid": single,
        "n_none_valid": none, "n_partially_valid": partial,
        "joint_support": joint / total if total else None,
        "missing_pattern_counts": dict(sorted(patterns.items())), "paired_values": paired,
        "mean": mean, "sample_sd": sd, "standard_error": se,
        "normal95_interval": [mean - 1.96 * se, mean + 1.96 * se] if se is not None else None,
        "interval_method": "Pointwise normal approximation; no simultaneous-coverage claim",
    }
