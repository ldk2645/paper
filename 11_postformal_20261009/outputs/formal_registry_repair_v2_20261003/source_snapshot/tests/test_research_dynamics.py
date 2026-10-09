"""Development dynamic protocols: lineage, references, censoring and scales."""
import copy
from dataclasses import replace
import json
import unittest
from unittest.mock import patch

from abm_jasss.research_config import ResearchConfig
from abm_jasss.research_dynamics import (
    run_continuation, run_dynamics, run_healthy_reference, run_recovery_branches,
    run_size_duration_checks, resolve_dynamics_spec, rebuild_dynamics_diagnostics,
)
from abm_jasss.research_world import ResearchWorld, canonical_hash


def small_config(**changes):
    values = dict(n_agents=8, n_topics=2, steps=12, final_window=3,
                  population_weights=(1., 1.), agenda_topics=(0,), advantaged_topic=1,
                  initial_items=4, arrivals_per_step=2, attention_budget=2,
                  survey_size=4, survey_interval=2, observation_window=2,
                  update_frequency=2, inference_grid=2, reference_agents=2,
                  response_threshold=.1, completion_followup=2)
    values.update(changes)
    return ResearchConfig(**values)


class ResearchDynamicsTests(unittest.TestCase):
    def test_return_path_inherits_each_predecessor_and_reproduces_direct_run(self):
        config = small_config()
        result = run_continuation(config, 501, alphas=(.2, .8), stage_ticks=3)
        records = result["diagnostics"]["stages"]
        self.assertEqual([record["alpha"] for record in records], [.2, .8, .8, .2])
        self.assertEqual([record["direction"] for record in records], ["forward"] * 2 + ["reverse"] * 2)
        self.assertEqual([record["start_tick"] for record in records], [0, 3, 6, 9])
        for index, record in enumerate(records):
            self.assertTrue(record["state_preserved"])
            self.assertEqual(record["input_snapshot_hash"], record["inherited_snapshot_hash"])
            if index:
                self.assertEqual(record["input_snapshot_hash"], records[index - 1]["output_snapshot_hash"])
                self.assertEqual(record["parent_world_id"], records[index - 1]["world_id"])
        first_reverse = result["worlds"][records[2]["name"]]
        forward_end = result["worlds"][records[1]["name"]]
        self.assertEqual(first_reverse.trajectory[:6], forward_end.trajectory)
        # Holding the endpoint unchanged for a second stage equals an ordinary
        # uninterrupted extension, including its queue and information history.
        direct = ResearchWorld.from_snapshot(forward_end.snapshot()).run(9)
        self.assertEqual(first_reverse.trajectory, direct.trajectory)
        self.assertEqual(first_reverse.events, direct.events)
        self.assertEqual(first_reverse.preferences.tolist(), direct.preferences.tolist())

    def test_continuation_extends_horizon_before_initialization(self):
        result = run_continuation(small_config(steps=6), 502, (.1, .9), 3)
        self.assertEqual(result["diagnostics"]["registration"]["config"]["steps"], 12)
        self.assertEqual(result["diagnostics"]["stages"][-1]["end_tick_exclusive"], 12)
        self.assertFalse(result["diagnostics"]["formal_ready"])
        for bad in ((.8, .2), (.2, .2), (.2,), (float("nan"), .9)):
            with self.subTest(alphas=bad), self.assertRaises(ValueError):
                run_continuation(small_config(), 502, bad, 3)

    def test_reference_uses_registered_independent_period_and_is_hash_checked(self):
        result = run_healthy_reference(small_config(alpha=0.), 601, 1, 4, .02, 2, 2)
        reference = result["reference"]
        values = [row["exposure_gap"] for row in result["world"].trajectory[1:5]]
        self.assertAlmostEqual(reference["value"], sum(values) / len(values))
        self.assertEqual(result["initial_snapshot"]["state"]["tick"], 0)
        self.assertTrue(reference["registration"]["registered_before_run"])
        self.assertFalse(reference["registration"]["substantive_health_validated"])
        self.assertEqual(reference["registration_hash"], canonical_hash(reference["registration"]))
        parent = ResearchWorld(small_config(), 602).run(5)
        altered = copy.deepcopy(reference)
        altered["value"] += .1
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            run_recovery_branches(parent, altered, {"control": {}}, 10)
        same_seed_parent = ResearchWorld(small_config(), 601).run(5)
        with self.assertRaisesRegex(ValueError, "independent"):
            run_recovery_branches(same_seed_parent, reference, {"control": {}}, 10)

    def test_recovery_branches_share_reference_parent_and_preintervention_baseline(self):
        config = small_config()
        healthy = run_healthy_reference(replace(config, alpha=0.), 701, 1, 4, .01, 2, 2)
        parent = ResearchWorld(config, 702).run(5)
        before = parent.snapshot()
        result = run_recovery_branches(parent, healthy["reference"],
                                       {"control": {}, "alpha0": {"alpha": 0.}}, 10)
        baseline = sum(row["exposure_gap"] for row in parent.trajectory[-2:]) / 2
        for name, world in result["worlds"].items():
            diagnostic = result["diagnostics"]["branches"][name]
            self.assertEqual(world.trajectory[:5], parent.trajectory)
            self.assertEqual(diagnostic["parent_snapshot_hash"], before["state_hash"])
            self.assertEqual(diagnostic["reference_hash"], healthy["reference"]["reference_hash"])
            self.assertEqual(diagnostic["start_step"], 4)
            self.assertEqual(diagnostic["observed_end"], 9)
            self.assertAlmostEqual(diagnostic["initial_rolling_mean"], baseline)
            self.assertTrue(diagnostic["conditional_on_candidate_reference"])
            self.assertIn("agenda_attention_share", diagnostic["window_summary"]["metrics"])
        self.assertEqual(parent.snapshot(), before)

    def test_no_health_reference_reports_improvement_without_recovery_claim(self):
        parent = ResearchWorld(small_config(), 703).run(4)
        result = run_recovery_branches(parent, None, {"control": {}}, 8)
        diagnostic = result["diagnostics"]["branches"]["control"]
        self.assertEqual(diagnostic["status"], "no_health_reference")
        self.assertIsNone(diagnostic["recovery_time"])
        self.assertFalse(diagnostic["conditional_on_candidate_reference"])

    def test_zero_candidate_reference_preserves_unrecovered_right_censoring(self):
        # A constructed zero-gap independent reference makes censor semantics
        # deterministic without requiring a treatment to improve the model.
        config = small_config(alpha=1., attention_budget=1, drift_rate=0.)
        healthy = run_healthy_reference(config, 711, 0, 1, 0., 1, 2)
        reference = copy.deepcopy(healthy["reference"])
        reference["value"] = 0.
        reference["reference_hash"] = canonical_hash({key: value for key, value in reference.items()
                                                      if key != "reference_hash"})
        parent = ResearchWorld(config, 712).run(4)
        result = run_recovery_branches(parent, reference, {"control": {}}, 8)
        diagnostic = result["diagnostics"]["branches"]["control"]
        self.assertEqual(diagnostic["status"], "right_censored")
        self.assertTrue(diagnostic["right_censored"])
        self.assertEqual(diagnostic["censor_time"], 4)
        self.assertIsNone(diagnostic["recovery_time"])

    def test_sizes_durations_and_initial_populations_are_registered_with_scales(self):
        config = small_config(n_agents=8, initial_items=4, arrivals_per_step=2, response_capacity=2)
        initial_conditions = {"balanced": (1., 1.), "skewed": (1., 3.)}
        result = run_size_duration_checks(config, 801, (8, 16), (6, 8), initial_conditions,
                                          supply_scaling="proportional", capacity_scaling="fixed")
        self.assertEqual(len(result["worlds"]), 8)
        for world in result["worlds"].values():
            self.assertEqual(world.config.arrivals_per_step / world.config.n_agents, .25)
            self.assertEqual(world.config.initial_items / world.config.n_agents, .5)
            self.assertEqual(world.config.response_capacity, 2)
        short = result["worlds"]["size_duration_balanced_n8_t6"]
        long = result["worlds"]["size_duration_balanced_n8_t8"]
        skewed = result["worlds"]["size_duration_skewed_n8_t6"]
        self.assertEqual(short.initial_state_hash, long.initial_state_hash)
        self.assertEqual(short.trajectory, long.trajectory[:6])
        self.assertNotEqual(short.initial_state_hash, skewed.initial_state_hash)
        self.assertEqual(skewed.config.population_weights, (1., 3.))
        proportional = run_size_duration_checks(config, 802, (16,), (6,), {"balanced": (1., 1.)},
                                                supply_scaling="fixed", capacity_scaling="proportional")
        world = next(iter(proportional["worlds"].values()))
        self.assertEqual(world.config.response_capacity, 4)
        self.assertEqual(world.config.arrivals_per_step, 2)

    def test_dynamic_suite_returns_serializable_evidence_and_expected_worlds(self):
        spec = {"alphas": [.2, .8], "stage_ticks": 2,
                "recovery_fork": 4, "recovery_end": 8,
                "reference_start": 1, "reference_end": 3,
                "recovery_window": 2, "recovery_consecutive": 2,
                "sizes": [8], "durations": [6], "initial_conditions": {"balanced": [1., 1.]}}
        result = run_dynamics(small_config(), 901, spec)
        self.assertEqual(len(result["worlds"]), 10)
        self.assertIn("healthy_candidate", result["worlds"])
        self.assertIn("recovery_parent", result["worlds"])
        self.assertIn("continuation_03_reverse", result["worlds"])
        self.assertFalse(result["diagnostics"]["formal_ready"])
        json.dumps(result["diagnostics"], allow_nan=False)
        json.dumps(result["snapshots"], allow_nan=False)
        world_snapshots = {name: world.snapshot() for name, world in result["worlds"].items()}
        with patch.object(ResearchWorld, "step", side_effect=AssertionError("Rebuild must not simulate")):
            rebuilt = rebuild_dynamics_diagnostics(small_config(), 901, spec, world_snapshots, result["snapshots"])
        self.assertEqual(canonical_hash(rebuilt), canonical_hash(result["diagnostics"]))
        altered = copy.deepcopy(result["snapshots"])
        key = "continuation_continuation_02_reverse_inherited"
        altered[key]["state"]["arrays"]["trust"][0] = .12345
        altered[key]["state_hash"] = canonical_hash(altered[key]["state"])
        with self.assertRaisesRegex(ValueError, "inherited state"):
            rebuild_dynamics_diagnostics(small_config(), 901, spec, world_snapshots, altered)

    def test_resolve_rejects_complete_invalid_design_before_world_creation(self):
        config = small_config()
        invalid = [{"unexpected": True}, {"stage_ticks": True}, {"alphas": [.8, .2]},
                   {"sizes": []}, {"sizes": [8, 8]}, {"durations": [0]},
                   {"initial_conditions": {"bad/path": [1., 1.]}},
                   {"initial_conditions": {"bad": [1., False]}},
                   {"initial_conditions": {"bad": [1.]}},
                   {"reference_start": 4, "reference_end": 3}, {"reference_seed": 55},
                   {"reference_seed": -1}, {"recovery_window": 31},
                   {"interventions": {"healthy_candidate": {}}},
                   {"interventions": {"x": {"response_enabled": False}}},
                   {"interventions": {"x": {"alpha": "0.5"}}}]
        with patch.object(ResearchWorld, "__init__", side_effect=AssertionError("Validation must not construct worlds")):
            good = resolve_dynamics_spec(config, 55)
            self.assertEqual(good["reference_seed"], 1_000_058)
            for spec in invalid:
                with self.subTest(spec=spec), self.assertRaises(ValueError):
                    resolve_dynamics_spec(config, 55, spec)

    def test_invalid_recovery_horizon_and_reference_window_fail(self):
        config = small_config()
        with self.assertRaises(ValueError):
            run_healthy_reference(config, 1001, 5, 4)
        with self.assertRaises(ValueError):
            run_healthy_reference(config, 1001, 0, 12)
        parent = ResearchWorld(config, 1002).run(2)
        with self.assertRaises(ValueError):
            run_recovery_branches(parent, None, {"control": {}}, 2)
        with self.assertRaises(ValueError):
            run_size_duration_checks(config, 1002, (8, 8), (6,), {"a": (1., 1.)})


if __name__ == "__main__":
    unittest.main()
