"""Derived-only repair regressions; the recorded formal endpoint is never rerun."""
import copy
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from abm_jasss.research_s1_cli import build_derived as historical_derived
from abm_jasss.research_world import ResearchWorld, canonical_hash, source_hash
from scripts.formal_artifacts import (NUMERIC_REPAIR_POLICY, SNAPSHOT_FILE, _validated_binding,
    read, save_world, sha256, validate_world_folder)
from scripts.formal_numeric_repair import (TOLERANCE, build_formal_derived,
    normalize_trajectory_distances)
from test_formal_runtime import fingerprint

ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTIC = ROOT / "outputs/formal_failure_diagnostic_20261003"
SIGNAL = [0.0, 0.27122641509433965, 0.5212264150943396, 0.20754716981132076]
ESTIMATE = [1.0, 0.0, 0.0, 0.0]


def reconstruction_roundoff_vector():
    # Python 3.12 sum compensates the original NumPy-only case. This vector
    # remains normalized within 1e-12 but also exercises legacy scalar-sum TV.
    value = SIGNAL[:]
    value[-1] += 16 * math.ulp(value[-1])
    return value


def fixture():
    row = {"step": 0, "P_true": ESTIMATE[:], "P_hat_gov": ESTIMATE[:],
           "S_public": None, "S_available": None, "E_exposure": None,
           "signal_estimate_distance": math.nextafter(1.0, math.inf),
           "estimate_input_packet_id": "packet", "available_packet_id": None,
           "has_data": True, "pending_count": 0, "responses_scheduled": 0,
           "responses_executed": 0, "trust_mean": .5, "preference_shift": 0.0}
    state = {"config": {"n_topics": 4}, "tick": 1, "queue": {},
             "packet_index": {"packet": {"signal": SIGNAL[:]}},
             "logs": {"trajectory": [row], "events": [], "government_estimates": []}}
    metadata = {"run_id": "fixture", "group_id": "fixture", "scenario": "E2", "condition": "I11",
                "analysis_config": {"steps": 1, "final_window": 1, "min_signal_coverage": 0.0,
                    "completion_start": 0, "completion_end": 0, "completion_followup": 0}}
    return state, metadata


class NumericBoundaryTests(unittest.TestCase):
    def test_recorded_one_ulp_is_audited_without_mutating_state(self):
        state, metadata = fixture()
        before = copy.deepcopy(state)
        with self.assertRaisesRegex(ValueError, "signal_estimate_distance"):
            historical_derived(state, metadata)
        result = build_formal_derived(state, metadata)
        self.assertEqual(state, before)
        self.assertEqual(result["summary"]["signal_estimate_distance"], 1.0)
        self.assertEqual(result["numeric_policy"], NUMERIC_REPAIR_POLICY)
        self.assertEqual(result["numeric_corrections"], [{"field": "signal_estimate_distance",
            "tick": 0, "source": "recorded", "raw": math.nextafter(1.0, math.inf),
            "normalized": 1.0, "tolerance": TOLERANCE}])

    def test_normal_case_equals_historical_values_with_empty_audit(self):
        state, metadata = fixture()
        state["logs"]["trajectory"][0]["signal_estimate_distance"] = 1.0
        expected = historical_derived(state, metadata)
        result = build_formal_derived(state, metadata)
        self.assertEqual(result.pop("numeric_corrections"), [])
        self.assertEqual(result.pop("numeric_policy"), NUMERIC_REPAIR_POLICY)
        self.assertEqual(result, expected)

    def test_none_remains_missing(self):
        state, metadata = fixture()
        state["logs"]["trajectory"][0]["signal_estimate_distance"] = None
        result = build_formal_derived(state, metadata)
        self.assertIsNone(result["summary"]["signal_estimate_distance"])
        self.assertEqual(result["numeric_corrections"], [])

    def test_tolerance_inside_outside_and_lower_boundary(self):
        for value, allowed in ((1 + TOLERANCE / 2, True),
                               (math.nextafter(1 + TOLERANCE, 1.0), True),
                               (math.nextafter(1 + TOLERANCE, math.inf), False),
                               (1 + 2 * TOLERANCE, False),
                               (-TOLERANCE, True), (-2 * TOLERANCE, False)):
            with self.subTest(value=value):
                state, _ = fixture()
                state["logs"]["trajectory"][0]["signal_estimate_distance"] = value
                if value < 0:
                    state["packet_index"]["packet"]["signal"] = ESTIMATE[:]
                if allowed:
                    normalized, audit = normalize_trajectory_distances(state)
                    self.assertEqual(normalized["logs"]["trajectory"][0]["signal_estimate_distance"],
                                     0.0 if value < 0 else 1.0)
                    self.assertEqual(len(audit), 1)
                else:
                    with self.assertRaisesRegex(ValueError, "boundary tolerance"):
                        normalize_trajectory_distances(state)

    def test_nonfinite_and_nonnumeric_distances_are_rejected(self):
        for value in (math.nan, math.inf, -math.inf, True, "1"):
            with self.subTest(value=value):
                state, _ = fixture()
                state["logs"]["trajectory"][0]["signal_estimate_distance"] = value
                with self.assertRaisesRegex(ValueError, "Nonfinite or nonnumeric"):
                    normalize_trajectory_distances(state)

    def test_repair_requires_valid_support_vectors(self):
        for vector in (None, [], [0., 1.], [0., .4, .4, .4],
                       [-1e-16, .5, .5, 1e-16], [math.nan, 0., 0., 1.],
                       [math.inf, 0., 0., 0.]):
            with self.subTest(vector=vector):
                state, _ = fixture()
                state["packet_index"]["packet"]["signal"] = vector
                with self.assertRaises(ValueError):
                    normalize_trajectory_distances(state)

    def test_forged_scalar_or_missing_packet_is_not_repaired(self):
        state, _ = fixture()
        state["packet_index"]["packet"]["signal"] = ESTIMATE[:]
        with self.assertRaisesRegex(ValueError, "disagrees"):
            normalize_trajectory_distances(state)
        state["packet_index"] = {}
        with self.assertRaisesRegex(ValueError, "Missing used packet"):
            normalize_trajectory_distances(state)

    def test_vector_reconstruction_boundary_is_also_audited(self):
        state, metadata = fixture()
        row = state["logs"]["trajectory"][0]
        row.update(P_true=reconstruction_roundoff_vector(), perception_error=1.0,
                   signal_estimate_distance=None)
        before = copy.deepcopy(state)
        self.assertGreater(historical_derived(state, metadata)["summary"]["perception_error"], 1.0)
        result = build_formal_derived(state, metadata)
        self.assertEqual(result["summary"]["perception_error"], 1.0)
        self.assertEqual(result["numeric_corrections"][0]["source"], "vector_reconstruction")
        self.assertEqual(result["numeric_corrections"][0]["field"], "perception_error")
        self.assertEqual(state, before)
        self.assertIn("P_hat_gov", row)

    def test_configuration_coverage_threshold_stays_strict(self):
        state, metadata = fixture()
        metadata["analysis_config"]["min_signal_coverage"] = math.nextafter(1., math.inf)
        with self.assertRaisesRegex(ValueError, "min_signal_coverage"):
            build_formal_derived(state, metadata)

    def test_cohort_vector_roundoff_preserves_original_events(self):
        state, metadata = fixture()
        first = state["logs"]["trajectory"][0]
        preference = reconstruction_roundoff_vector()
        first.update(P_true=preference[:], P_hat_gov=None, signal_estimate_distance=None)
        second = dict(first, step=1, P_true=ESTIMATE[:])
        state["logs"]["trajectory"].append(second)
        state["tick"] = 2
        state["logs"]["government_estimates"] = [
            {"estimate_input_packet_id": None, "estimate_updated_at": None}]
        state["logs"]["events"] = [{"event_id": "event", "topic": 0, "trigger_step": 0,
            "due_step": 1, "execution_step": 1, "P_trigger": preference[:],
            "P_execution": ESTIMATE[:], "information_ref": {}}]
        metadata["analysis_config"].update(steps=2, final_window=2, completion_end=1)
        before = copy.deepcopy(state)
        result = build_formal_derived(state, metadata)
        self.assertEqual(state, before)
        cohort = result["summary"]["executed_cohorts"][0]
        self.assertEqual(cohort["targeting_error_trigger"], 1.0)
        self.assertEqual(cohort["preference_shift_during_wait"], 1.0)
        self.assertEqual(result["summary"]["targeting_error_trigger"], 1.0)
        self.assertEqual(result["summary"]["signed_targeting_change"], -1.0)
        self.assertEqual({r["source"] for r in result["numeric_corrections"]},
                         {"cohort_vector_reconstruction"})


class RecordedEndpointRegression(unittest.TestCase):
    def test_recorded_snapshot_export_and_read_only_reconstruction(self):
        # Only read the archived diagnostic endpoint. No new formal simulation,
        # synthetic replacement seed, or invented registry release is involved.
        job = read(DIAGNOSTIC / "job.json")
        snapshot = read(DIAGNOSTIC / "i11_distance_inspection/snapshot.json.gz")
        registry = ROOT / "outputs/formal_registry_20261003"
        self.assertIn(job, read(registry / "resolved_design.json"))
        self.assertEqual(snapshot["state"]["seed"], job["seed"])
        self.assertEqual(snapshot["state"]["source_hash"], source_hash())
        original_hash = canonical_hash(snapshot)
        original_file_hash = sha256(DIAGNOSTIC / "i11_distance_inspection/snapshot.json.gz")
        report = {"status": "passed", "formal_ready": True,
                  "registry_hash": sha256(registry / "manifest.json"),
                  "specification_hash": canonical_hash(read(registry / "configuration.json")),
                  "source_hash": source_hash()}
        binding = _validated_binding(report, job)
        with tempfile.TemporaryDirectory() as temporary, \
             patch.object(ResearchWorld, "run", side_effect=AssertionError("no physical run")), \
             patch.object(ResearchWorld, "step", side_effect=AssertionError("no physical step")):
            output = Path(temporary)
            world = ResearchWorld.from_snapshot(snapshot)
            name = "E2_" + job["group_id"] + "_I11"
            derived = save_world(world, output, "diagnostic-regression-only", name, job["group_id"],
                                 "E2", "I11", source_hash(), registry_binding=binding)
            self.assertEqual(len(derived["numeric_corrections"]), 5)
            self.assertEqual({r["field"] for r in derived["numeric_corrections"]},
                             {"signal_estimate_distance"})
            self.assertEqual(read(output / "raw" / name / SNAPSHOT_FILE), snapshot)
            before = fingerprint(output)
            rebuilt = validate_world_folder(output / "raw" / name, source_hash(), registry_binding=binding)
            self.assertEqual(rebuilt, derived)
            self.assertEqual(fingerprint(output), before)
            self.assertEqual(world.snapshot(), snapshot)
        self.assertEqual(canonical_hash(snapshot), original_hash)
        self.assertEqual(sha256(DIAGNOSTIC / "i11_distance_inspection/snapshot.json.gz"), original_file_hash)


if __name__ == "__main__":
    unittest.main()
