"""Explicit derived-only TV boundary repair; frozen physical data stay intact.

The absolute 1e-12 tolerance covers arithmetic roundoff far below the registered
0.02 precision target. It is not a substantive effect or missingness threshold.
No vector is renormalized. Every repaired scalar needs valid, finite probability
vectors and an independently accumulated TV agreeing within the same tolerance.
Configuration validation and the historical engine/summary functions are intact.
"""
import copy
import math
from numbers import Real
import statistics

from abm_jasss.research_outcomes import DISTANCE_KEYS
from abm_jasss.research_s1_cli import build_derived

TOLERANCE = 1e-12
_VECTOR_FIELDS = {
    "platform_representation_gap": "S_public", "perception_error": "P_hat_gov",
    "exposure_gap": "E_exposure", "visible_signal_current_gap": "S_available",
}
_COHORT_FIELDS = ("targeting_error_trigger", "targeting_error_execution",
                  "preference_shift_during_wait")
NUMERIC_REPAIR_POLICY = {
    "schema_version": "formal-numeric-repair-1",
    "absolute_tolerance": TOLERANCE,
    "relative_tolerance": 0.0,
    "probability_sum_absolute_tolerance": TOLERANCE,
    "tv_consistency_absolute_tolerance": TOLERANCE,
    "distance_interval": [0.0, 1.0],
    "trajectory_fields": list(DISTANCE_KEYS),
    "cohort_fields": list(_COHORT_FIELDS),
    "scope": "derived_observations_only",
    "raw_artifacts": "unchanged",
    "missing_values": "preserve_none",
    "configuration_thresholds": "strict_unchanged",
    "invalid_values": "reject_nonfinite_invalid_vectors_and_excess_beyond_tolerance",
    "repair_evidence": "field_tick_source_raw_normalized_tolerance",
    "reconstructed_boundary": "verified_scalar_in_temporary_analysis_view",
}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _number(value, context):
    _require(isinstance(value, Real) and not isinstance(value, bool)
             and math.isfinite(float(value)), f"Nonfinite or nonnumeric {context}")
    return float(value)


def _bounded(value, context):
    if value is None:
        return None, False
    value = _number(value, context)
    excess = max(-value, value - 1.0, 0.0)
    _require(excess <= TOLERANCE, f"Distance outside boundary tolerance: {context}")
    return min(1.0, max(0.0, value)), excess > 0.0


def _vector(value, topics, context):
    _require(isinstance(value, (list, tuple)) and len(value) == topics and topics > 0,
             f"Missing or invalid probability vector: {context}")
    values = [_number(v, context) for v in value]
    _require(all(0.0 <= v <= 1.0 for v in values)
             and abs(math.fsum(values) - 1.0) <= TOLERANCE,
             f"Invalid probability vector: {context}")
    return values


def _validated_tv(left, right, topics, context):
    left = _vector(left, topics, context + "/left")
    right = _vector(right, topics, context + "/right")
    value = 0.5 * math.fsum(abs(a - b) for a, b in zip(left, right))
    _bounded(value, context + "/recomputed TV")
    return value


def _support_vectors(state, row, field):
    if field in _VECTOR_FIELDS:
        return row.get("P_true"), row.get(_VECTOR_FIELDS[field])
    packets = state.get("packet_index", {})
    if field == "signal_estimate_distance":
        packet = packets.get(row.get("estimate_input_packet_id"))
        _require(isinstance(packet, dict), "Missing used packet for boundary repair")
        return packet.get("signal"), row.get("P_hat_gov")
    packet = packets.get(row.get("available_packet_id"))
    _require(isinstance(packet, dict), "Missing available packet for boundary repair")
    topics = state["config"]["n_topics"]
    steps, weights = packet.get("valid_steps"), packet.get("weights")
    _require(isinstance(steps, (list, tuple)) and steps and isinstance(weights, (list, tuple))
             and len(steps) == len(weights), "Invalid matched-packet support")
    weights = _vector(weights, len(steps), "matched packet weights")
    vectors = [_vector(state.get("truth_history", {}).get(str(step)), topics,
                       "matched packet preference") for step in steps]
    matched = [math.fsum(weight * vector[k] for weight, vector in zip(weights, vectors))
               for k in range(topics)]
    return matched, row.get("S_available")


def _record(corrections, field, tick, raw, normalized, source, **extra):
    corrections.append({"field": field, "tick": tick, "source": source,
                        "raw": float(raw), "normalized": normalized,
                        "tolerance": TOLERANCE, **extra})


def normalize_trajectory_distances(state):
    """Return a temporary analysis view and audit; never alter any input object.

    Historical summarize_world reconstructs four distances from vectors. If that
    reconstruction itself crosses a boundary, we validate the original vectors
    here and supply the verified scalar in a copied row without its reconstruction
    vector. This affects only the temporary summary view, never snapshot or logs.
    """
    corrections, rows = [], []
    topics = state["config"]["n_topics"]
    for original in state["logs"]["trajectory"]:
        row = dict(original)
        for field in DISTANCE_KEYS:
            raw = original.get(field)
            normalized, recorded_bad = _bounded(raw, field)
            vector_field = _VECTOR_FIELDS.get(field)
            reconstructs = vector_field is not None and vector_field in original
            left, right = original.get("P_true"), original.get(vector_field)
            reconstructed = None
            if reconstructs and left is not None and right is not None:
                # Match the unchanged historical summarizer's arithmetic exactly.
                reconstructed = 0.5 * sum(abs(a - b) for a, b in zip(left, right))
            reconstructed_normalized, reconstructed_bad = _bounded(reconstructed, field)
            if not (recorded_bad or reconstructed_bad):
                continue
            support = _support_vectors(state, original, field)
            tv = _validated_tv(*support, topics, field)
            if raw is not None:
                _require(abs(float(raw) - tv) <= TOLERANCE,
                         f"Recorded distance disagrees with repair vectors: {field}")
            if recorded_bad:
                row[field] = normalized
                _record(corrections, field, original["step"], raw, normalized, "recorded")
            if reconstructed_bad:
                _require(abs(reconstructed - tv) <= TOLERANCE,
                         f"Reconstructed distance disagrees with repair vectors: {field}")
                row[field] = reconstructed_normalized
                row.pop(vector_field)
                _record(corrections, field, original["step"], reconstructed,
                        reconstructed_normalized, "vector_reconstruction")
        rows.append(row)
    if not corrections:
        return state, corrections
    analysis = dict(state)
    analysis["logs"] = dict(state["logs"], trajectory=rows)
    return analysis, corrections


def _normalize_cohorts(derived, topics, corrections):
    summary = derived["summary"]
    changed = False
    for cohort in summary["executed_cohorts"]:
        cohort_changed = False
        for field in _COHORT_FIELDS:
            raw = cohort[field]
            normalized, needs_repair = _bounded(raw, field)
            if not needs_repair:
                continue
            left, right = ((cohort["P_trigger"], cohort["P_execution"])
                           if field == "preference_shift_during_wait" else
                           (cohort["target_distribution"], cohort["P_trigger"]
                            if field == "targeting_error_trigger" else cohort["P_execution"]))
            tv = _validated_tv(left, right, topics, field)
            _require(abs(float(raw) - tv) <= TOLERANCE,
                     f"Cohort distance disagrees with repair vectors: {field}")
            cohort[field] = normalized
            _record(corrections, field, cohort["execution_step"], raw, normalized,
                    "cohort_vector_reconstruction", trigger_tick=cohort["trigger_step"])
            cohort_changed = changed = True
        if cohort_changed:
            cohort["signed_targeting_change"] = (cohort["targeting_error_execution"]
                                                  - cohort["targeting_error_trigger"])
    if changed:
        for field in ("targeting_error_trigger", "targeting_error_execution", "signed_targeting_change"):
            summary[field] = statistics.fmean(row[field] for row in summary["executed_cohorts"])


def build_formal_derived(state, metadata):
    """The single export/reconstruction route for explicitly repaired summaries."""
    analysis, corrections = normalize_trajectory_distances(state)
    derived = build_derived(analysis, metadata)
    _normalize_cohorts(derived, state["config"]["n_topics"], corrections)
    derived["numeric_policy"] = copy.deepcopy(NUMERIC_REPAIR_POLICY)
    derived["numeric_corrections"] = corrections
    return derived
