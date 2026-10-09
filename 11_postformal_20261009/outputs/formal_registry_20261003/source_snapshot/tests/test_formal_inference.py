"""Frozen formal inference, verified on analytic distributions and synthetic worlds."""
import copy
import json
import math
import statistics
import unittest

from scripts.formal_inference import (
    INFERENCE_POLICY, PRIMARY_METRICS, REGISTERED_CONTRASTS,
    build_formal_inference, holm_adjust, paired_t_inference,
    student_t_critical, student_t_two_sided_p, validate_inference_spec,
)


METRIC = PRIMARY_METRICS[0]


def specification(n_low=32, n_high=36):
    return {
        "alphas": [.25, .75],
        "parent_ids_by_alpha": {"0.25": list(range(n_low)), "0.75": list(range(n_high))},
        "metrics": list(PRIMARY_METRICS), "contrasts": copy.deepcopy(REGISTERED_CONTRASTS),
        "inference": copy.deepcopy(INFERENCE_POLICY),
    }


def synthetic_records(spec):
    records = []
    for family, contrasts in spec["contrasts"].items():
        arms = sorted({arm for coefficients in contrasts.values() for arm in coefficients})
        for alpha in spec["alphas"]:
            for parent in spec["parent_ids_by_alpha"][str(alpha)]:
                for arm_index, arm in enumerate(arms):
                    # Shared mother-world variation cancels; arm-dependent
                    # variation remains and provides a nonzero paired variance.
                    value = .25 + (parent % 5) / 32 + arm_index / 64
                    value += (parent % 3) * (arm_index + 1) / 256
                    records.append({
                        "family": family, "alpha": alpha, "parent_id": parent,
                        "arm": arm, "status": "complete",
                        "metrics": {metric: value for metric in PRIMARY_METRICS},
                    })
    return records


def group(analysis, family="E2", alpha=.25):
    return next(item for item in analysis["groups"]
                if item["family"] == family and item["alpha"] == alpha)


def result(analysis, contrast="pref_given_rule0", metric=METRIC, **kwargs):
    return group(analysis, **kwargs)["contrasts"][contrast][metric]


def all_results(analysis):
    return [item for g in analysis["groups"] for outcomes in g["contrasts"].values()
            for item in outcomes.values()]


class StudentTTests(unittest.TestCase):
    def test_distribution_tails_match_independent_closed_forms(self):
        for statistic in (1e-8, .001, .1, 1., 10., 1e8):
            with self.subTest(statistic=statistic):
                cauchy_tail = 2 / math.pi * math.atan(1 / statistic)
                root = math.sqrt(statistic * statistic + 2)
                df2_tail = 2 / (root * (root + statistic))
                for df, expected in ((1, cauchy_tail), (2, df2_tail)):
                    actual = student_t_two_sided_p(statistic, df)
                    self.assertLess(abs(actual / expected - 1), 2e-10)
                    self.assertEqual(actual, student_t_two_sided_p(-statistic, df))
        self.assertEqual(student_t_two_sided_p(0, 29), 1)
        self.assertAlmostEqual(student_t_two_sided_p(1e200, 1) / (2e-200 / math.pi),
                               1., places=12)

    def test_critical_values_match_published_t_table(self):
        # NIST t distribution table, .975 column (rounded table values).
        # https://www.itl.nist.gov/div898/handbook/eda/section3/eda3672.htm
        for df, expected in ((1, 12.706), (2, 4.303), (10, 2.228),
                             (29, 2.045), (30, 2.042), (100, 1.984)):
            with self.subTest(df=df):
                value = student_t_critical(df)
                self.assertAlmostEqual(value, expected, delta=.0005)
                self.assertAlmostEqual(student_t_two_sided_p(value, df), .05, places=12)
        self.assertGreater(student_t_critical(999), 1.9599)
        self.assertLess(student_t_critical(999), student_t_critical(183))

    def test_small_tail_at_formal_df_matches_independent_density_integration(self):
        # Simpson integration of the t density is independent of incomplete
        # beta evaluation and catches catastrophic cancellation in tail p.
        for df in (29, 183, 999):
            normalizer = math.exp(math.lgamma((df + 1) / 2) - math.lgamma(df / 2))
            normalizer /= math.sqrt(df * math.pi)

            def density(x):
                return normalizer * (1 + x * x / df) ** (-(df + 1) / 2)

            left, right, steps = 10., 100., 90000
            spacing = (right - left) / steps
            summed = density(left) + density(right)
            summed += math.fsum((4 if i % 2 else 2) * density(left + spacing * i)
                               for i in range(1, steps))
            probability = 2 * summed * spacing / 3
            actual = student_t_two_sided_p(left, df)
            self.assertLess(abs(actual / probability - 1), 1e-8)

    def test_t_interval_uses_paired_sample_variance_and_df(self):
        # mean=1/8; n=32; sample variance=32/31*(1/16)^2 exactly.
        values = [1 / 16, 3 / 16] * 16
        item = paired_t_inference(values)
        expected_se = 1 / (16 * math.sqrt(31))
        self.assertEqual(item["status"], "estimated")
        self.assertEqual(item["degrees_of_freedom"], 31)
        self.assertAlmostEqual(item["standard_error"], expected_se)
        self.assertAlmostEqual(item["t_statistic"], 2 * math.sqrt(31))
        half_width = student_t_critical(31) * expected_se
        self.assertAlmostEqual(item["confidence_half_width"], half_width)
        self.assertAlmostEqual(item["confidence_interval"][0], .125 - half_width, places=14)
        self.assertAlmostEqual(item["confidence_interval"][1], .125 + half_width, places=14)
        self.assertFalse(item["additional_sampling"])
        self.assertEqual(item["observed_target_half_width_met"], half_width <= .02)

    def test_small_sample_and_constant_samples_do_not_claim_certainty(self):
        samples = ([], [None] * 35, [1.0] * 29, [0.0] * 30, [1.0] * 30,
                   [0.0, 1e-13] * 15)
        for values in samples:
            with self.subTest(values=values[:2], n=len(values)):
                item = paired_t_inference(values)
                self.assertIsNone(item["confidence_interval"])
                self.assertIsNone(item["p_value_two_sided"])
                self.assertEqual(item["p_value_for_holm"], 1)
                self.assertFalse(item["additional_sampling"])
        item = paired_t_inference([.25] * 30)
        self.assertEqual(item["status"], "degenerate_sample_variance")
        self.assertEqual(item["mean"], .25)
        self.assertEqual(item["sample_sd"], 0)

    def test_numerical_tolerance_is_absolute_sd_not_effect_size(self):
        self.assertEqual(INFERENCE_POLICY["sample_sd_numerical_tolerance"], 1e-12)
        # Equal opposite signs have mean zero but sufficient variation.
        item = paired_t_inference([-2e-12, 2e-12] * 15)
        self.assertEqual(item["status"], "estimated")
        self.assertEqual(item["p_value_two_sided"], 1)
        self.assertGreater(item["confidence_half_width"], 0)

    def test_joint_minimum_and_operational_gap_rules_are_prespecified(self):
        values = [-.1, .2] * 15
        self.assertEqual(paired_t_inference(values)["status"], "estimated")
        self.assertEqual(paired_t_inference(values[:-1] + [None])["status"],
                         "insufficient_joint_support")
        item = paired_t_inference(values, operationally_complete=False)
        self.assertEqual(item["status"], "operationally_incomplete")
        self.assertIsNotNone(item["mean"])
        self.assertIsNone(item["confidence_interval"])
        self.assertIsNone(item["p_value_two_sided"])

    def test_extreme_tails_remain_positive_and_invalid_parameters_reject(self):
        self.assertGreater(student_t_two_sided_p(1e200, 999), 0)
        for statistic, df in ((math.nan, 30), (math.inf, 30), (True, 30),
                              (1, 0), (1, -1), (1, 1.5), (1, True)):
            with self.subTest(statistic=statistic, df=df), self.assertRaises(ValueError):
                student_t_two_sided_p(statistic, df)
        for value in (math.nan, math.inf, True, "0.1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                paired_t_inference([value])


class HolmTests(unittest.TestCase):
    def test_stepdown_cumulative_max_ties_and_unavailable_test(self):
        adjusted = holm_adjust([.01, .04, .03, None, .01])
        for actual, expected in zip(adjusted, [.05, .09, .09, 1., .05]):
            self.assertAlmostEqual(actual, expected)
        self.assertEqual(holm_adjust([None] * 102), [1.] * 102)
        self.assertEqual(holm_adjust([]), [])

    def test_missing_tests_preserve_entire_registered_family(self):
        adjusted = holm_adjust([.0001] + [None] * 101)
        self.assertAlmostEqual(adjusted[0], .0102)
        self.assertEqual(adjusted[1:], [1.] * 101)
        for value in (-.1, 1.1, math.nan, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                holm_adjust([value])


class FormalRegistryTests(unittest.TestCase):
    def test_full_family_is_102_and_strata_keep_different_registered_denominators(self):
        spec = specification()
        records = synthetic_records(spec)
        analysis = build_formal_inference(records, spec)
        self.assertEqual(analysis["comparison_count"], 102)
        self.assertEqual(len(all_results(analysis)), 102)
        self.assertEqual(len({item["comparison_id"] for item in all_results(analysis)}), 102)
        self.assertEqual(result(analysis)["n_total"], 32)
        self.assertEqual(result(analysis, alpha=.75)["n_total"], 36)
        self.assertTrue(analysis["operationally_complete"])
        self.assertEqual(analysis["inference"], INFERENCE_POLICY)
        self.assertFalse(analysis["additional_sampling"])
        json.dumps(analysis, allow_nan=False)
        self.assertEqual(analysis, build_formal_inference(reversed(records), spec))

    def test_four_arm_interaction_is_computed_within_mother_world(self):
        spec = specification()
        records = synthetic_records(spec)
        expected = []
        coefficients = REGISTERED_CONTRASTS["E2"]["interaction"]
        for parent in spec["parent_ids_by_alpha"]["0.25"]:
            matching = {row["arm"]: row["metrics"][METRIC] for row in records
                        if row["family"] == "E2" and row["alpha"] == .25
                        and row["parent_id"] == parent}
            expected.append(sum(coefficients[arm] * value for arm, value in matching.items()))
        item = result(build_formal_inference(records, spec), "interaction")
        self.assertEqual(list(item["paired_values"].values()), expected)
        self.assertEqual(item["mean"], statistics.mean(expected))
        self.assertEqual(item["sample_sd"], statistics.stdev(expected))
        self.assertNotIn("normal95_interval", item)

    def test_undefined_metric_retains_joint_support_and_changes_only_affected_contrasts(self):
        spec = specification()
        records = synthetic_records(spec)
        for row in records:
            if row["family"] == "E2" and row["alpha"] == .25 and row["arm"] == "I10":
                if row["parent_id"] < 3:
                    row["metrics"][METRIC] = None
        analysis = build_formal_inference(records, spec)
        item = result(analysis)
        self.assertEqual(item["n_total"], 32)
        self.assertEqual(item["n_joint_valid"], 29)
        self.assertEqual(item["n_single_sided_valid"], 3)
        self.assertEqual(item["joint_support"], 29 / 32)
        self.assertIsNone(item["paired_values"]["0"])
        self.assertEqual(sum(item["missing_pattern_counts"].values()), 32)
        self.assertEqual(item["status"], "insufficient_joint_support")
        self.assertEqual(item["p_value_holm"], 1)
        self.assertFalse(item["reject_holm_0_05"])
        self.assertTrue(group(analysis)["operationally_complete"])
        self.assertEqual(result(analysis, "rule_given_pref0")["n_joint_valid"], 32)
        self.assertEqual(result(analysis, metric=PRIMARY_METRICS[1])["n_joint_valid"], 32)

    def test_missing_and_failed_runs_are_operational_not_structural_missingness(self):
        spec = specification()
        records = synthetic_records(spec)
        removed = records.pop(0)
        failed = records[0]
        failed["status"] = "failed"
        failed["metrics"] = {}
        analysis = build_formal_inference(records, spec)
        affected = group(analysis)
        self.assertEqual(affected["missing_records"],
                         [{"parent_id": str(removed["parent_id"]), "arm": removed["arm"]}])
        self.assertEqual(affected["failed_records"],
                         [{"parent_id": str(failed["parent_id"]), "arm": failed["arm"]}])
        self.assertFalse(analysis["operationally_complete"])
        for outcomes in affected["contrasts"].values():
            for item in outcomes.values():
                self.assertEqual(item["status"], "operationally_incomplete")
                self.assertIsNone(item["confidence_interval"])
                self.assertEqual(item["p_value_for_holm"], 1)
        self.assertEqual(result(analysis, alpha=.75)["status"], "estimated")
        self.assertEqual(analysis["comparison_count"], 102)

    def test_holm_is_applied_once_over_every_family_stratum_and_metric(self):
        spec = specification()
        analysis = build_formal_inference(synthetic_records(spec), spec)
        items = all_results(analysis)
        ordered = sorted(items, key=lambda item: item["p_value_for_holm"])
        running = 0.
        for rank, item in enumerate(ordered):
            running = min(1., max(running, (102 - rank) * item["p_value_for_holm"]))
            self.assertEqual(item["p_value_holm"], running)
            self.assertEqual(item["reject_holm_0_05"],
                             item["status"] == "estimated" and running <= .05)

    def test_registry_changes_and_duplicate_world_records_fail_closed(self):
        original = specification()
        mutations = []
        for key, value in (("metrics", [METRIC]), ("alphas", [.25]), ("contrasts", {"E2": {}})):
            changed = copy.deepcopy(original)
            changed[key] = value
            mutations.append(changed)
        changed = copy.deepcopy(original)
        changed["inference"]["family_size"] = 51
        mutations.append(changed)
        changed = copy.deepcopy(original)
        changed["parent_ids_by_alpha"]["0.25"] = [1, "1"]
        mutations.append(changed)
        changed = copy.deepcopy(original)
        changed["parent_ids_by_alpha"]["0.75"] = []
        mutations.append(changed)
        for spec in mutations:
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                validate_inference_spec(spec)
        records = synthetic_records(original)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            build_formal_inference(records + [records[0]], original)
        records[0]["parent_id"] = "unregistered"
        with self.assertRaisesRegex(ValueError, "Unregistered mother"):
            build_formal_inference(records, original)

    def test_invalid_measured_values_cannot_enter_formal_inference(self):
        spec = specification()
        for value in (math.nan, math.inf, -.1, 1.1, True):
            records = synthetic_records(spec)
            records[0]["metrics"][METRIC] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                build_formal_inference(records, spec)
        records = synthetic_records(spec)
        records[0]["metrics"].pop(METRIC)
        with self.assertRaisesRegex(ValueError, "missing a registered metric"):
            build_formal_inference(records, spec)
        records = synthetic_records(spec)
        records[0]["status"] = "failed"
        with self.assertRaisesRegex(ValueError, "Failed records cannot"):
            build_formal_inference(records, spec)


if __name__ == "__main__":
    unittest.main()
