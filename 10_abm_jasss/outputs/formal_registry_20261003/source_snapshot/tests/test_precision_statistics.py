"""Mother-world pairing and fixed-budget pilot diagnostics on synthetic data."""
import copy
import json
import math
import statistics
import unittest

from abm_jasss.research_outcomes import DEFAULT_CONTRASTS, precision_plan
from scripts.precision_statistics import (
    PRIMARY_METRICS, assess_precision_stability, build_precision_analysis,
)


METRIC = PRIMARY_METRICS[0]


def spec(parents, *, alphas=(.25,), contrasts=None, metrics=(METRIC,), **kwargs):
    return {"parent_ids": list(parents), "alphas": list(alphas), "metrics": list(metrics),
            "contrasts": contrasts or {"E2": {"difference": {"I10": 1, "I00": -1}}},
            **kwargs}


def record(parent, arm, value, *, alpha=.25, family="E2", status="complete"):
    return {"family": family, "alpha": alpha, "parent_id": parent, "arm": arm,
            "status": status, "metrics": {metric: value for metric in PRIMARY_METRICS}}


def result(analysis, contrast="difference", metric=METRIC, group=0):
    return analysis["groups"][group]["contrasts"][contrast][metric]


def difference_records(parents, values, *, alpha=.25, family="E2"):
    records = []
    for parent, value in zip(parents, values):
        records.extend([record(parent, "I00", .5, alpha=alpha, family=family),
                        record(parent, "I10", .5 + value if value is not None else None,
                               alpha=alpha, family=family)])
    return records


class PrecisionAnalysisTests(unittest.TestCase):
    def test_pairing_cancels_shared_world_variation_and_retains_missing_parents(self):
        records = [record(1, "I00", .1), record(1, "I10", .3),
                   record(2, "I00", .8), record(2, "I10", 1),
                   record(3, "I00", .4), record(3, "I10", None),
                   record(4, "I00", None), record(4, "I10", None)]
        analysis = build_precision_analysis(records, spec(range(1, 5)))
        paired = result(analysis)
        self.assertEqual(paired["n_total"], 4)
        self.assertEqual(paired["n_joint_valid"], 2)
        self.assertEqual(paired["n_single_sided_valid"], 1)
        self.assertEqual(paired["n_none_valid"], 1)
        self.assertIsNone(paired["paired_values"]["3"])
        self.assertIsNone(paired["paired_values"]["4"])
        self.assertAlmostEqual(paired["sample_variance"], 0)
        self.assertEqual(paired["precision_plan"], precision_plan([.3 - .1, 1 - .8, None, None]))
        self.assertTrue(analysis["groups"][0]["shared_plan"]["operationally_complete"])
        json.dumps(analysis, allow_nan=False)

    def test_interaction_is_a_per_parent_four_arm_contrast(self):
        values = {1: {"I00": .1, "I10": .2, "I01": .2, "I11": .8},
                  2: {"I00": .2, "I10": .6, "I01": .4, "I11": .3},
                  3: {"I00": .2, "I10": .6, "I01": None, "I11": .3}}
        records = [record(parent, arm, value) for parent, arms in values.items()
                   for arm, value in arms.items()]
        analysis = build_precision_analysis(records, spec(values, contrasts={"E2": DEFAULT_CONTRASTS}))
        paired = result(analysis, "interaction")
        expected = [.8 - .2 - .2 + .1, .3 - .6 - .4 + .2]
        self.assertAlmostEqual(paired["sample_variance"], statistics.variance(expected))
        self.assertIsNone(paired["paired_values"]["3"])
        self.assertEqual(paired["missing_pattern_counts"], {"1101": 1, "1111": 2})
        self.assertEqual(paired["n_joint_valid"], 2)
        self.assertEqual(result(analysis, "pref_given_rule0")["n_joint_valid"], 3)

    def test_wilson_support_uses_registered_parent_denominator(self):
        records = difference_records(range(20), [.1] * 10 + [None] * 10)
        paired = result(build_precision_analysis(records, spec(range(20))))
        lower, upper = paired["joint_support_wilson95"]
        self.assertLess(lower, .5)
        self.assertGreater(upper, .5)
        self.assertAlmostEqual(lower + upper, 1)
        self.assertEqual(paired["precision_plan"]["required_total_uncapped"], math.ceil(30 / lower))

    def test_alpha_strata_and_families_have_separate_shared_requirements(self):
        families = {family: {"difference": {"I10": 1, "I00": -1}}
                    for family in ("E2", "E4")}
        records = []
        for family in families:
            for alpha in (.25, .75):
                values = [-.5, .5] * 10 if (family, alpha) == ("E4", .75) else [.1] * 20
                records.extend(difference_records(range(20), values, family=family, alpha=alpha))
        analysis = build_precision_analysis(records, spec(range(20), alphas=(.25, .75), contrasts=families))
        low, high = analysis["shared_by_alpha"]
        self.assertEqual(low["fixed_total"], 36)
        self.assertEqual(high["fixed_total"], 1000)
        self.assertFalse(high["precision_target_feasible"])
        self.assertTrue(high["budget_capped"])
        self.assertGreater(high["required_total_uncapped"], 1000)
        self.assertEqual(high["limiting_items"], [f"E4/difference/{METRIC}"])
        self.assertTrue(all(group["n_parent_worlds"] == 20 for group in analysis["groups"]))

    def test_all_primary_metrics_enter_maximum_shared_n(self):
        records = difference_records(range(20), [0] * 20)
        for index, item in enumerate(records):
            if item["arm"] == "I10":
                item["metrics"][PRIMARY_METRICS[2]] = 0 if index % 4 == 1 else 1
        analysis = build_precision_analysis(records, spec(range(20), metrics=PRIMARY_METRICS))
        shared = analysis["groups"][0]["shared_plan"]
        self.assertEqual(shared["limiting_items"], [f"difference/{PRIMARY_METRICS[2]}"])
        self.assertEqual(shared["fixed_total"], 1000)

    def test_unestimable_outcome_is_not_silently_removed_from_shared_n(self):
        records = difference_records(range(20), [.1] * 20)
        for item in records:
            item["metrics"][PRIMARY_METRICS[2]] = None
        analysis = build_precision_analysis(records, spec(range(20), metrics=PRIMARY_METRICS))
        plan = analysis["shared_by_alpha"][0]
        self.assertIsNone(plan["fixed_total"])
        self.assertEqual(plan["max_estimable_required_total"], 36)
        self.assertEqual(plan["unplannable_items"], [f"E2/difference/{PRIMARY_METRICS[2]}"])
        self.assertFalse(plan["precision_target_feasible"])

    def test_absent_arms_and_failed_worlds_are_preserved_and_block_acceptance(self):
        records = difference_records(range(20), [.1] * 20)
        records.pop()
        records[1] = record(0, "I10", None, status="failed")
        analysis = build_precision_analysis(records, spec(range(20)))
        group = analysis["groups"][0]
        self.assertEqual(group["missing_records"], [{"parent_id": "19", "arm": "I10"}])
        self.assertEqual(group["failed_records"], [{"parent_id": "0", "arm": "I10"}])
        self.assertEqual(result(analysis)["n_total"], 20)
        self.assertEqual(result(analysis)["n_joint_valid"], 18)
        self.assertEqual(group["shared_plan"]["status"], "incomplete_pilot")
        self.assertFalse(analysis["shared_by_alpha"][0]["precision_target_feasible"])

    def test_missing_entire_parent_remains_in_denominator(self):
        analysis = build_precision_analysis([], spec(range(20)))
        paired = result(analysis)
        self.assertEqual(list(paired["paired_values"].values()), [None] * 20)
        self.assertEqual(paired["precision_plan"]["pilot_total"], 20)
        self.assertIsNone(paired["sample_variance"])

    def test_duplicate_and_unregistered_records_are_rejected(self):
        row = record(0, "I00", .5)
        invalid = [([row, row], spec([0])),
                   ([row], spec([0, "0"])),
                   ([{**row, "parent_id": 1}], spec([0])),
                   ([{**row, "family": "unexpected"}], spec([0])),
                   ([{**row, "arm": "unexpected"}], spec([0])),
                   ([{**row, "alpha": .75}], spec([0])),
                   ([{**row, "status": "pending"}], spec([0]))]
        for rows, design in invalid:
            with self.subTest(rows=rows, design=design), self.assertRaises(ValueError):
                build_precision_analysis(rows, design)

    def test_nonfinite_out_of_range_and_missing_metrics_are_rejected(self):
        for value in (math.nan, math.inf, -.1, 1.1, True, "0.5"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                build_precision_analysis([record(0, "I00", value)], spec([0]))
        for row in ({**record(0, "I00", .5), "metrics": {}},
                    record(0, "I00", .5, status="failed")):
            with self.assertRaises(ValueError):
                build_precision_analysis([row], spec([0]))

    def test_invalid_contrasts_and_settings_are_rejected_before_empty_data(self):
        for coefficients in ({"I00": 1}, {"I00": 0}, {"I00": math.nan, "I10": -1}):
            with self.subTest(coefficients=coefficients), self.assertRaises(ValueError):
                build_precision_analysis([], spec([0], contrasts={"E2": {"bad": coefficients}}))
        for settings in ({"target_half_width": 0}, {"min_valid": 1}, {"max_total": 0}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                build_precision_analysis([], spec([0], **settings))


class PrecisionStabilityTests(unittest.TestCase):
    def analyses(self, first_values, later_values):
        first_records = difference_records(range(20), first_values)
        all_records = first_records + difference_records(range(20, 40), later_values)
        return (build_precision_analysis(first_records, spec(range(20))),
                build_precision_analysis(all_records, spec(range(40))))

    def test_stable_variance_support_diagnostic_stops_at_registered_budget(self):
        first, second = self.analyses([-.1, .1] * 10, [-.1, .1] * 10)
        diagnostic = assess_precision_stability(first, second)
        self.assertTrue(diagnostic["all_items_stable"])
        self.assertEqual(diagnostic["pilot_stop"], "fixed_budget_40_per_alpha")
        self.assertFalse(diagnostic["additional_pilot_sampling"])
        self.assertFalse(diagnostic["formal_ready"])
        json.dumps(diagnostic, allow_nan=False)

    def test_instability_cannot_authorize_extra_sampling(self):
        first, second = self.analyses([-.01, .01] * 10, [-.4, .4] * 10)
        diagnostic = assess_precision_stability(first, second)
        self.assertFalse(diagnostic["all_items_stable"])
        self.assertFalse(diagnostic["items"][0]["variance_stable"])
        self.assertFalse(diagnostic["additional_pilot_sampling"])

    def test_zero_variance_edges_and_insufficient_support(self):
        for first_values, later_values, expected in (
            ([0] * 20, [0] * 20, True),
            ([0] * 20, [-.1, .1] * 10, False),
            ([None] * 20, [0] * 20, False),
            ([0] * 10 + [None] * 10, [0] * 10 + [None] * 10, False),
        ):
            with self.subTest(expected=expected, first_values=first_values):
                diagnostic = assess_precision_stability(*self.analyses(first_values, later_values))
                self.assertEqual(diagnostic["all_items_stable"], expected)

    def test_support_change_is_checked_even_when_variance_is_zero(self):
        first, second = self.analyses([0] * 20, [0] * 10 + [None] * 10)
        diagnostic = assess_precision_stability(first, second)
        item = diagnostic["items"][0]
        self.assertTrue(item["variance_stable"])
        self.assertFalse(item["support_stable"])
        self.assertTrue(item["sufficient_joint_valid"])

    def test_inclusive_support_boundary_tolerates_only_float_roundoff(self):
        # 14/20 -> 32/40 is exactly +.10, represented as .10000000000000009.
        first, second = self.analyses([0] * 14 + [None] * 6, [0] * 18 + [None] * 2)
        diagnostic = assess_precision_stability(first, second)
        self.assertTrue(diagnostic["all_items_stable"])
        self.assertGreater(diagnostic["items"][0]["support_absolute_change"], .10)
        # The next possible support increment remains outside the threshold.
        first, second = self.analyses([0] * 14 + [None] * 6, [0] * 19 + [None])
        self.assertFalse(assess_precision_stability(first, second)["items"][0]["support_stable"])

    def test_inclusive_variance_boundary_tolerates_only_float_roundoff(self):
        first, second = self.analyses([0] * 20, [0] * 20)
        result(first)["sample_variance"] = .03
        result(second)["sample_variance"] = .04
        self.assertTrue(assess_precision_stability(first, second)["items"][0]["variance_stable"])
        result(second)["sample_variance"] = .040001
        self.assertFalse(assess_precision_stability(first, second)["items"][0]["variance_stable"])

    def test_effects_and_intervals_are_not_used_in_diagnostic(self):
        first, second = self.analyses([-.1, .1] * 10, [-.1, .1] * 10)
        expected = assess_precision_stability(first, second)
        for analysis, effect in ((first, -1e99), (second, 1e99)):
            item = result(analysis)
            item["mean"] = effect
            item["normal95_interval"] = [effect, effect]
            item["paired_values"] = {key: effect for key in item["paired_values"]}
            item["precision_plan"]["paired_mean"] = effect
        self.assertEqual(assess_precision_stability(first, second), expected)

    def test_changed_design_or_non_nested_parent_registry_is_rejected(self):
        first, second = self.analyses([0] * 20, [0] * 20)
        for mutation in ("parents", "settings", "coefficients", "contrasts"):
            modified = copy.deepcopy(second)
            if mutation == "parents":
                modified["parent_ids"].reverse()
            elif mutation == "settings":
                modified["planning_settings"]["target_half_width"] = .03
            elif mutation == "coefficients":
                result(modified)["coefficients"] = {"I00": 1, "I10": -1}
            else:
                modified["groups"][0]["contrasts"] = {}
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                assess_precision_stability(first, modified)


if __name__ == "__main__":
    unittest.main()
