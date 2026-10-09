"""Post-process response-topic mismatch without modifying simulation outputs.

The response vector is an equal-weight distribution of executed response
topics within one (trigger step, due step) cohort. It measures topical focus;
it is not a resource allocation, welfare measure, or heat-control magnitude.
The change in mismatch between trigger and execution is signed and descriptive.
It does not identify a causal effect of delay or decompose distances additively.
"""
from collections import defaultdict
import math
from numbers import Integral

import numpy as np


def _integer(value, name, minimum=0):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    if isinstance(value, Integral):
        result = int(value)
    elif isinstance(value, str) and value.strip().isdigit():
        result = int(value)
    else:
        raise ValueError(f"{name} must be an integer")
    if result < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return result


def _number(value, name):
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be finite") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _vector(row, prefix, n_topics):
    try:
        result = np.array([_number(row[f"{prefix}_{k}"], prefix) for k in range(n_topics)])
    except KeyError as exc:
        raise ValueError(f"Missing {prefix} topic in trajectory row") from exc
    if (result < 0).any() or (result > 1).any() or not math.isclose(float(result.sum()), 1, abs_tol=1e-9):
        raise ValueError(f"{prefix} must be a probability vector")
    return result


def _tv(left, right):
    return float(.5 * np.abs(left - right).sum())


def response_target_diagnostics(rows, events, config, pending_responses=None, *, validate_references=True):
    """Return ``executed_cohorts`` and ``pending_cohorts`` from one saved world.

    ``rows`` accepts CSV-reader dictionaries or the model's numeric dictionaries.
    ``events`` accepts the saved event list; ``config`` supplies ``active_arm``,
    ``n_topics`` and ``steps``. Pass the artifact's ``pending_responses`` to check
    its exact agreement with scheduled actions; when omitted, infer terminal
    pending actions from the schedules. No action produces two empty lists.

    Event matching and time checks are always enforced. The optional
    ``validate_references`` flag additionally checks recorded signal values and
    any embedded preference, attention, or error fields against the trajectory.
    Disabling it does not permit duplicate, missing, early, or overdue actions.

    Executed cohorts have equal-weight target distributions, both time-indexed
    public preference vectors, both ``response_target_mismatch`` values, their
    signed change, and the preference drift between those two observations.
    ``representation_error_at_trigger`` is TV(public preference, attention).
    ``sensing_error_at_trigger`` is TV(public preference, active-arm estimate).
    ``signal_estimate_distance_at_trigger`` is TV(attention, active-arm estimate).
    Pending cohorts contain counts and time references only, with right censoring.
    """
    try:
        n_topics = _integer(config["n_topics"], "n_topics", 2)
        steps = _integer(config["steps"], "steps", 1)
        arm = config["active_arm"]
    except KeyError as exc:
        raise ValueError(f"Missing configuration field: {exc.args[0]}") from exc
    if arm not in ("platform", "survey", "fused", "oracle"):
        raise ValueError("Unknown active_arm")
    if not isinstance(validate_references, bool):
        raise ValueError("validate_references must be boolean")
    rows = list(rows)
    if len(rows) != steps:
        raise ValueError("Trajectory must contain every configured step exactly once")
    truth, attention, estimate = {}, {}, {}
    for expected, row in enumerate(rows):
        if "step" not in row or _integer(row["step"], "row step") != expected:
            raise ValueError("Trajectory steps must be ordered, unique, and consecutive from zero")
        truth[expected] = _vector(row, "truth", n_topics)
        attention[expected] = _vector(row, "attention", n_topics)
        estimate[expected] = _vector(row, f"estimate_{arm}", n_topics)

    def action_key(record):
        try:
            trigger = _integer(record["trigger_step"], "trigger_step")
            due = _integer(record["due_step"], "due_step")
            topic = _integer(record["topic"], "topic")
        except KeyError as exc:
            raise ValueError(f"Missing action reference: {exc.args[0]}") from exc
        if trigger >= steps or due <= trigger or topic >= n_topics:
            raise ValueError("Action has invalid trigger/due time or topic")
        return trigger, due, topic

    def check_value(record, field, expected):
        if field in record and not math.isclose(_number(record[field], field), float(expected),
                                                rel_tol=1e-9, abs_tol=1e-10):
            raise ValueError(f"Event {field} disagrees with its referenced trajectory")

    scheduled, executed = {}, {}
    for event in events:
        kind = event.get("kind")
        if kind == "routine_publication":
            continue
        if kind not in ("response_scheduled", "response_executed"):
            raise ValueError(f"Unknown event kind: {kind}")
        key = action_key(event)
        trigger, due, topic = key
        if "step" not in event:
            raise ValueError("Response event is missing step")
        event_step = _integer(event["step"], "event step")
        if event_step >= steps or event_step != (trigger if kind == "response_scheduled" else due):
            raise ValueError("Response event step does not match its trigger/due step")
        bucket = scheduled if kind == "response_scheduled" else executed
        if key in bucket:
            raise ValueError(f"Duplicate {kind} event")
        bucket[key] = event
        if validate_references:
            if "signal_value" not in event:
                raise ValueError("Response event is missing signal_value")
            check_value(event, "signal_value", estimate[trigger][topic])
            if kind == "response_scheduled":
                check_value(event, "target_preference_at_trigger", truth[trigger][topic])
                check_value(event, "target_attention_at_trigger", attention[trigger][topic])
                check_value(event, "target_estimation_error", abs(estimate[trigger][topic] - truth[trigger][topic]))
            else:
                check_value(event, "target_preference_at_execution", truth[due][topic])
    if not set(executed).issubset(scheduled):
        raise ValueError("Executed response has no matching scheduled event")
    # A topic cannot acquire a second plan before the first plan is executed.
    by_topic = defaultdict(list)
    for trigger, due, topic in scheduled:
        by_topic[topic].append((trigger, due))
    for intervals in by_topic.values():
        intervals.sort()
        if any(current[0] < previous[1] for previous, current in zip(intervals, intervals[1:])):
            raise ValueError("Multiple response plans overlap for the same topic")
    inferred_pending = set(scheduled) - set(executed)
    if any(due < steps for _, due, _ in inferred_pending):
        raise ValueError("A response due within the saved horizon is missing its execution")
    if pending_responses is not None:
        recorded_pending = set()
        for record in pending_responses:
            key = action_key(record)
            if key in recorded_pending:
                raise ValueError("Duplicate pending response")
            recorded_pending.add(key)
            if validate_references:
                if "signal_value" not in record:
                    raise ValueError("Pending response is missing signal_value")
                check_value(record, "signal_value", estimate[key[0]][key[2]])
        if recorded_pending != inferred_pending:
            raise ValueError("Pending artifact disagrees with scheduled and executed events")

    grouped_executed, grouped_pending = defaultdict(list), defaultdict(list)
    for trigger, due, topic in executed:
        grouped_executed[(trigger, due)].append(topic)
    for trigger, due, topic in inferred_pending:
        grouped_pending[(trigger, due)].append(topic)
    cohorts = []
    for (trigger, due), topics in sorted(grouped_executed.items()):
        response = np.bincount(topics, minlength=n_topics).astype(float) / len(topics)
        mismatch_trigger = _tv(response, truth[trigger])
        mismatch_execution = _tv(response, truth[due])
        cohorts.append({
            "step": due, "trigger_step": trigger, "due_step": due, "n_actions": len(topics),
            "target_distribution": response.tolist(),
            "public_preference_at_trigger": truth[trigger].tolist(),
            "public_preference_at_execution": truth[due].tolist(),
            "response_target_mismatch_at_trigger": mismatch_trigger,
            "response_target_mismatch_at_execution": mismatch_execution,
            "signed_mismatch_change": mismatch_execution - mismatch_trigger,
            "preference_drift_between_trigger_and_execution": _tv(truth[trigger], truth[due]),
            "representation_error_at_trigger": _tv(truth[trigger], attention[trigger]),
            "sensing_error_at_trigger": _tv(truth[trigger], estimate[trigger]),
            "signal_estimate_distance_at_trigger": _tv(attention[trigger], estimate[trigger]),
        })
    pending_cohorts = [
        {"step": trigger, "trigger_step": trigger, "due_step": due,
         "n_actions": len(topics), "right_censored": True}
        for (trigger, due), topics in sorted(grouped_pending.items())]
    return {"executed_cohorts": cohorts, "pending_cohorts": pending_cohorts}
