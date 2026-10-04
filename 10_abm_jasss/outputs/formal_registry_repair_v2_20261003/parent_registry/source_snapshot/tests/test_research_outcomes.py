"""Contract tests for research outcomes, conditional support and censoring."""
import json
import math
import unittest

from abm_jasss.research_outcomes import (
    paired_contrast, precision_plan, recovery_diagnostic, summarize_world,
)


def trajectory(preferences):
    return [{"step": step, "P_true": p, "E_exposure": [.5, .5],
             "S_public": [.5, .5], "S_available": [.5, .5],
             "P_hat_gov": [.5, .5], "has_data": True,
             "visible_signal_matched_gap": .1, "signal_estimate_distance": 0.0}
            for step, p in enumerate(preferences)]


def action(event_id, topic, trigger, due, execution, rows):
    return {"event_id": event_id, "topic": topic, "trigger_step": trigger,
            "due_step": due, "execution_step": execution,
            "P_trigger": rows[trigger]["P_true"],
            "P_execution": None if execution is None else rows[execution]["P_true"]}


def config(steps, **kwargs):
    return {"steps": steps, "final_window": steps, "min_signal_coverage": .8,
            "completion_start": 0, "completion_end": steps - 1,
            "completion_followup": 2, **kwargs}


class WorldSummaryTests(unittest.TestCase):
    def test_no_response_is_missing_targeting_not_zero(self):
        result = summarize_world(trajectory([[.7, .3]] * 4), [], config(4))
        self.assertEqual(result["execution_count"], 0)
        self.assertEqual(result["execution_coverage"], 0)
        self.assertIsNone(result["targeting_error_trigger"])
        self.assertIsNone(result["targeting_error_execution"])
        self.assertIsNone(result["waiting_time"])
        self.assertIsNone(result["response_completion_L"])
        self.assertEqual(result["completion"]["status"], "empty_cohort")
        json.dumps(result, allow_nan=False)

    def test_zero_delay_executes_same_tick_and_completes_at_L_zero(self):
        rows = trajectory([[.7, .3]] * 3)
        events = [action("a", 0, 1, 1, 1, rows)]
        result = summarize_world(rows, events, config(3, completion_followup=0))
        self.assertEqual(result["waiting_time"], 0)
        self.assertAlmostEqual(result["targeting_error_trigger"], .3)
        self.assertAlmostEqual(result["targeting_error_execution"], .3)
        self.assertEqual(result["response_completion_L"], 1)

    def test_actions_are_aggregated_before_equal_cohort_averaging(self):
        rows = trajectory([[.5, .5], [.6, .4], [.6, .4], [.8, .2], [.2, .8], [.2, .8]])
        events = [action("a", 0, 1, 3, 3, rows), action("b", 1, 1, 3, 3, rows),
                  action("c", 0, 4, 5, 5, rows)]
        result = summarize_world(rows, events, config(6, final_window=3))
        self.assertEqual(result["executed_cohort_count"], 2)
        self.assertEqual(result["executed_cohorts"][0]["target_distribution"], [.5, .5])
        self.assertAlmostEqual(result["targeting_error_trigger"], (.1 + .8) / 2)
        self.assertAlmostEqual(result["targeting_error_execution"], (.3 + .8) / 2)
        self.assertEqual(result["execution_count"], 3)
        self.assertAlmostEqual(result["execution_coverage"], 2 / 3)
        self.assertAlmostEqual(result["waiting_time"], 5 / 3)
        self.assertEqual(result["scheduled_count"], 1)
        self.assertEqual(result["scheduled_count_total"], 3)

    def test_targeting_uses_execution_window_not_completion_enrollment(self):
        rows = trajectory([[.7, .3]] * 5)
        events = [action("a", 0, 0, 1, 1, rows), action("b", 1, 1, 4, 4, rows)]
        result = summarize_world(rows, events, config(5, final_window=1,
                                                     completion_start=0, completion_end=0,
                                                     completion_followup=1))
        self.assertAlmostEqual(result["targeting_error_trigger"], .7)
        self.assertEqual(result["response_completion_L"], 1)
        self.assertEqual(result["completion"]["n_enrolled"], 1)
        self.assertEqual(result["execution_count_total"], 2)

    def test_completion_separates_known_failure_unknown_and_early_known_success(self):
        rows = trajectory([[.7, .3]] * 6)
        events = [action("a", 0, 0, 1, 1, rows), action("b", 1, 2, 9, None, rows),
                  action("c", 0, 4, 8, None, rows), action("d", 1, 3, 5, 5, rows)]
        result = summarize_world(rows, events, config(10, completion_end=4, completion_followup=3))
        completion = result["completion"]
        self.assertIsNone(result["response_completion_L"])
        self.assertEqual(completion["completed_within_L"], 2)
        self.assertEqual(completion["not_completed_within_L"], 1)
        self.assertEqual(completion["unknown_right_censored"], 1)
        self.assertEqual(completion["pending_not_yet_due"], 2)
        self.assertEqual(completion["lower_bound"], .5)
        self.assertEqual(completion["upper_bound"], .75)
        self.assertEqual(result["pending_events"][0]["censor_wait"], 3)

    def test_completed_plans_are_known_before_full_followup_horizon(self):
        rows = trajectory([[.7, .3]] * 5)
        events = [action("a", 0, 3, 4, 4, rows)]
        result = summarize_world(rows, events, config(10, completion_start=3, completion_end=3,
                                                     completion_followup=4))
        self.assertEqual(result["response_completion_L"], 1)
        self.assertEqual(result["completion"]["status"], "fully_ascertained")

    def test_future_enrollment_makes_whole_cohort_incomplete(self):
        rows = trajectory([[.7, .3]] * 2)
        events = [action("a", 0, 0, 1, 1, rows)]
        result = summarize_world(rows, events, config(10, completion_end=7))
        self.assertIsNone(result["response_completion_L"])
        self.assertEqual(result["completion"]["status"], "incomplete_enrollment")
        self.assertIsNone(result["completion"]["upper_bound"])

    def test_late_execution_misses_L_without_becoming_pending(self):
        rows = trajectory([[.7, .3]] * 6)
        result = summarize_world(rows, [action("a", 0, 0, 4, 4, rows)],
                                 config(6, completion_end=0, completion_followup=2))
        self.assertEqual(result["response_completion_L"], 0)
        self.assertEqual(result["pending_count"], 0)
        self.assertEqual(result["completion"]["not_completed_within_L"], 1)

    def test_missing_signal_does_not_become_uniform_or_zero(self):
        rows = trajectory([[.7, .3]] * 4)
        rows[3]["S_public"] = None
        result = summarize_world(rows, [], config(4))
        self.assertIsNone(result["platform_representation_gap"])
        coverage = result["metric_coverage"]["platform_representation_gap"]
        self.assertEqual(coverage["coverage"], .75)
        self.assertAlmostEqual(coverage["mean_valid_ticks"], .2)
        self.assertAlmostEqual(result["exposure_gap"], .2)

    def test_prior_diagnostic_separate_from_data_estimate(self):
        rows = trajectory([[.7, .3]] * 4)
        for row in rows:
            row["has_data"] = False
        result = summarize_world(rows, [], config(4))
        self.assertIsNone(result["perception_error"])
        self.assertAlmostEqual(result["prior_perception_error"], .2)
        self.assertEqual(result["prior_estimate_ticks"], 4)

    def test_truncated_window_denominator_remains_frozen(self):
        result = summarize_world(trajectory([[.7, .3]] * 8), [], config(10, final_window=4))
        self.assertEqual(result["observed_window_ticks"], 2)
        self.assertEqual(result["metric_coverage"]["exposure_gap"]["coverage"], .5)
        self.assertIsNone(result["platform_representation_gap"])

    def test_inconsistent_event_or_distribution_is_rejected(self):
        rows = trajectory([[.7, .3]] * 4)
        good = action("a", 0, 1, 2, 2, rows)
        for bad in [dict(good, P_trigger=[.5, .5]), dict(good, due_step=3),
                    dict(good, execution_step=None), dict(good, topic=2)]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                summarize_world(rows, [bad], config(4))
        with self.assertRaises(ValueError):
            summarize_world(rows, [good, good], config(4))
        rows[0]["E_exposure"] = [0, 0]
        with self.assertRaises(ValueError):
            summarize_world(rows, [], config(4))

    def test_distance_disagreement_and_nan_rejected(self):
        rows = trajectory([[.7, .3]] * 2)
        rows[0]["exposure_gap"] = 0
        with self.assertRaises(ValueError):
            summarize_world(rows, [], config(2))
        rows[0]["exposure_gap"] = math.nan
        with self.assertRaises(ValueError):
            summarize_world(rows, [], config(2))


class RecoveryTests(unittest.TestCase):
    def run_recovery(self, values, **kwargs):
        options = {"key": "exposure_gap", "reference": .2, "tolerance": .1,
                   "window": 1, "consecutive": 2, "start_step": 0, **kwargs}
        return recovery_diagnostic([{"step": i, "exposure_gap": value} for i, value in enumerate(values)], **options)

    def test_no_reference_reports_improvement_without_recovery(self):
        result = self.run_recovery([.8, .7, .6], reference=None)
        self.assertEqual(result["status"], "no_health_reference")
        self.assertAlmostEqual(result["improvement_from_start"], .2)
        self.assertIsNone(result["recovery_time"])
        self.assertFalse(result["right_censored"])

    def test_healthy_initial_state_requires_no_recovery_and_reports_rebound(self):
        result = self.run_recovery([.2, .1, .7, .8])
        self.assertEqual(result["status"], "not_required")
        self.assertIsNone(result["recovery_time"])
        self.assertEqual(result["rebound_count"], 1)

    def test_sustained_recovery_confirmation_and_rebound(self):
        result = self.run_recovery([.8, .2, .1, .7, .2, .2, .8])
        self.assertEqual(result["status"], "recovered")
        self.assertEqual(result["recovery_time"], 2)
        self.assertEqual(result["recovery_onset_step"], 1)
        self.assertEqual(result["rebound_count"], 2)

    def test_missing_tick_breaks_sustained_recovery(self):
        result = self.run_recovery([.8, .2, None, .2, .8])
        self.assertEqual(result["status"], "right_censored")
        self.assertTrue(result["right_censored"])
        self.assertEqual(result["censor_time"], 4)

    def test_rolling_window_requires_complete_history(self):
        result = self.run_recovery([.8, .2, .2], window=2)
        self.assertEqual(result["status"], "initial_state_unobserved")
        result = self.run_recovery([.8, .8, .2, .2, .2], window=2, start_step=1)
        self.assertEqual(result["status"], "recovered")
        self.assertEqual(result["recovery_confirmed_step"], 4)


class PrecisionAndContrastTests(unittest.TestCase):
    def test_pilot_variance_uses_sample_sd_and_joint_support(self):
        plan = precision_plan([0, .1, None])
        self.assertAlmostEqual(plan["paired_sample_sd"], math.sqrt(.005))
        self.assertEqual(plan["required_valid"], 49)
        self.assertAlmostEqual(plan["joint_support"], 2 / 3)
        self.assertEqual(plan["pilot_joint_invalid"], 1)
        self.assertGreater(plan["fixed_total"], math.ceil(49 / (2 / 3)))
        self.assertFalse(plan["formal_ready"])
        json.dumps(plan, allow_nan=False)

    def test_insufficient_pilot_and_budget_limit_are_explicit(self):
        for values in ([], [None, None], [0, None]):
            plan = precision_plan(values)
            self.assertIsNone(plan["fixed_total"])
            self.assertEqual(plan["status"], "insufficient_pilot_variance")
            json.dumps(plan, allow_nan=False)
        plan = precision_plan([0, 1])
        self.assertEqual(plan["fixed_total"], 1000)
        self.assertTrue(plan["budget_capped"])
        self.assertFalse(plan["precision_target_feasible"])

    def test_zero_variance_retains_minimum_and_uncertain_support(self):
        plan = precision_plan([.1] * 20)
        self.assertEqual(plan["required_valid"], 30)
        self.assertGreater(plan["fixed_total"], 30)
        self.assertEqual(plan["paired_sample_sd"], 0)

    def test_joint_support_not_marginal_support_controls_pair_and_interaction(self):
        worlds = {"a": {"I00": .4, "I10": .3, "I01": .35, "I11": .2},
                  "b": {"I00": .2, "I10": None, "I01": .1, "I11": None},
                  "c": {"I00": None, "I10": .3, "I01": None, "I11": None},
                  "d": {"I00": None, "I10": None, "I01": None, "I11": None}}
        results = paired_contrast(worlds)
        pref = results["pref_given_rule0"]
        self.assertEqual(pref["n_total"], 4)
        self.assertEqual(pref["n_joint_valid"], 1)
        self.assertEqual(pref["n_single_sided_valid"], 2)
        self.assertEqual(pref["n_none_valid"], 1)
        self.assertAlmostEqual(pref["mean"], -.1)
        self.assertIsNone(pref["normal95_interval"])
        self.assertIsNone(pref["paired_values"]["b"])
        self.assertAlmostEqual(results["interaction"]["mean"], -.05)
        self.assertEqual(results["interaction"]["n_joint_valid"], 1)
        plan = precision_plan(pref["paired_values"].values())
        self.assertEqual(plan["pilot_joint_invalid"], 3)
        json.dumps(results, allow_nan=False)

    def test_parent_differences_supply_variance_not_independent_cell_variance(self):
        results = paired_contrast({"a": {"B0": .1, "B1": .2},
                                   "b": {"B0": .8, "B1": .9}},
                                  {"B1": 1, "B0": -1})
        self.assertAlmostEqual(results["mean"], .1)
        self.assertAlmostEqual(results["sample_sd"], 0)
        self.assertEqual(results["n_joint_valid"], 2)
        self.assertEqual(len(results["normal95_interval"]), 2)

    def test_nan_and_invalid_contrasts_rejected(self):
        with self.assertRaises(ValueError):
            precision_plan([math.nan, 0])
        with self.assertRaises(ValueError):
            paired_contrast({"a": {"I00": 0, "I10": math.inf}})
        with self.assertRaises(ValueError):
            paired_contrast({}, {"I00": 1})


if __name__ == "__main__":
    unittest.main()
