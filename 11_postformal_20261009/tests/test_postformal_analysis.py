"""Synthetic paired records test estimands without running study seeds."""
import copy
import statistics
import unittest
from unittest.mock import patch

from postformal.simulation import analysis
from postformal.simulation.common import AUXILIARY, E2, PRIMARY
from scripts.formal_inference import holm_adjust


def fixture(n=40):
    spec = {"variants": [{"id": name, "branches": ["B0", "B1"],
                           "closed": {"delay0": {"government_delay": 0}}, "replay_delays": [0, 3]}
                          for name in ("baseline", "no_drift")],
            "alphas": [.25, .75], "seeds": list(range(920120, 920120 + n)),
            "inference": {"holm_families": ["within_variant", "effect_change"], "target_half_width": .05}}
    records, auxiliary = [], []
    for v, variant in enumerate(spec["variants"]):
        for alpha in spec["alphas"]:
            for i, seed in enumerate(spec["seeds"]):
                epsilon = (i - (n - 1) / 2) * .002
                e2 = {"I00": .20 + .05 * v, "I10": .30 + .07 * v + epsilon * (v + 1),
                      "I01": .40 + .08 * v, "I11": .55 + .15 * v + 2 * epsilon * (v + 1)}
                values = [("E2", arm, e2[arm]) for arm in E2]
                values += [("E4", "B0", .3), ("E4", "B1", .301 + .001 * v + epsilon),
                           ("E3_closed", "baseline", .3), ("E3_closed", "delay0", .32 + epsilon),
                           ("E3_replay", "delay0", .35), ("E3_replay", "delay3", .36 + epsilon)]
                for family, arm, value in values:
                    identity = {"variant": variant["id"], "alpha": alpha, "parent_id": seed,
                                "family": family, "arm": arm, "status": "complete"}
                    records.append({**identity, "metrics": {metric: value for metric in PRIMARY}})
                    auxiliary.append({**identity, "values": {metric: value for metric in AUXILIARY}})
    return records, auxiliary, spec


def selected(rows, *, kind="within_variant", variant="no_drift", contrast="interaction", metric=PRIMARY[0]):
    return next(r for r in rows if r["analysis_family"] == kind and r["variant"] == variant
                and r["alpha"] == .25 and r["family"] == "E2" and r["contrast"] == contrast
                and r["metric"] == metric)


class PostformalAnalysisTests(unittest.TestCase):
    def test_interaction_and_effect_change_are_computed_within_each_parent(self):
        records, auxiliary, spec = fixture()
        rows, aux, paired = analysis.build_tables(records, auxiliary, spec)
        variant = selected(rows)
        change = selected(rows, kind="effect_change")
        self.assertAlmostEqual(variant["mean"], .10)
        self.assertAlmostEqual(change["mean"], .05)
        self.assertEqual(variant["n_joint_valid"], 40)
        self.assertEqual(change["n_joint_valid"], 40)
        observed = [r["value"] for r in paired if r["analysis_family"] == "effect_change"
                    and r["variant"] == "no_drift" and r["alpha"] == .25 and r["family"] == "E2"
                    and r["contrast"] == "interaction" and r["metric"] == PRIMARY[0]]
        self.assertEqual(len(observed), 40)
        self.assertAlmostEqual(observed[0], .05 - 19.5 * .002)
        self.assertAlmostEqual(change["sample_sd"], statistics.stdev(observed))
        self.assertEqual(len(change["support_terms"]), 8)
        self.assertEqual(change["support_patterns"], {"11111111": 40})
        self.assertTrue(all(r["n_total"] == 40 for r in aux))

    def test_effect_change_uses_common_support_across_both_variants(self):
        records, auxiliary, spec = fixture()
        seeds = spec["seeds"]
        for record in records:
            if record["alpha"] != .25 or record["family"] != "E2":
                continue
            if ((record["parent_id"] == seeds[0] and record["variant"] == "baseline" and record["arm"] == "I00")
                    or (record["parent_id"] == seeds[1] and record["variant"] == "no_drift" and record["arm"] == "I10")
                    or record["parent_id"] == seeds[2]):
                record["metrics"][PRIMARY[0]] = None
        rows, _, paired = analysis.build_tables(records, auxiliary, spec)
        self.assertEqual(selected(rows)["n_joint_valid"], 38)
        change = selected(rows, kind="effect_change")
        self.assertEqual(change["n_joint_valid"], 37)
        self.assertEqual(change["n_none_valid"], 1)
        self.assertEqual(change["n_partially_valid"], 2)
        observed = [r for r in paired if r["analysis_family"] == "effect_change" and r["variant"] == "no_drift"
                    and r["alpha"] == .25 and r["family"] == "E2" and r["contrast"] == "interaction"
                    and r["metric"] == PRIMARY[0]]
        self.assertTrue(all(r["value"] is None for r in observed[:3]))
        self.assertAlmostEqual(change["mean"], statistics.mean(r["value"] for r in observed[3:]))

    def test_holm_adjustment_uses_two_complete_independent_families(self):
        records, auxiliary, spec = fixture()
        with patch.object(analysis, "holm_adjust", wraps=holm_adjust) as adjust:
            rows, _, _ = analysis.build_tables(records, auxiliary, spec)
        self.assertEqual(adjust.call_count, 2)
        self.assertEqual([len(call.args[0]) for call in adjust.call_args_list], [96, 48])
        for kind, size in (("within_variant", 96), ("effect_change", 48)):
            family = [r for r in rows if r["analysis_family"] == kind]
            self.assertTrue(all(r["holm_family_size"] == size for r in family))
            expected = holm_adjust([r["p_value_two_sided"] for r in family])
            self.assertEqual([r["p_value_holm"] for r in family], expected)
        pooled = holm_adjust([r["p_value_two_sided"] for r in rows])
        self.assertNotEqual([r["p_value_holm"] for r in rows], pooled)

    def test_missing_metrics_and_degenerate_variance_remain_noninferential(self):
        records, auxiliary, spec = fixture()
        for record in records:
            record["metrics"][PRIMARY[1]] = None
            record["metrics"][PRIMARY[2]] = .5
        rows, _, _ = analysis.build_tables(records, auxiliary, spec)
        missing = selected(rows, metric=PRIMARY[1])
        degenerate = selected(rows, metric=PRIMARY[2])
        self.assertEqual(missing["status"], "insufficient_joint_support")
        self.assertEqual(missing["n_none_valid"], 40)
        self.assertEqual(missing["n_joint_valid"], 0)
        self.assertIsNone(missing["mean"])
        self.assertEqual(degenerate["status"], "degenerate_sample_variance")
        self.assertEqual(degenerate["n_joint_valid"], 40)
        self.assertEqual(degenerate["mean"], 0.)
        for row in (missing, degenerate):
            self.assertIsNone(row["ci_lower"])
            self.assertIsNone(row["ci_upper"])
            self.assertIsNone(row["p_value_two_sided"])
            self.assertEqual(row["p_value_holm"], 1.)
            self.assertFalse(row["reject_holm_0_05"])
            self.assertIsNone(row["observed_target_half_width_met"])
            self.assertFalse(row["additional_sampling"])

    def test_fewer_than_thirty_joint_parents_keep_only_descriptive_estimates(self):
        records, auxiliary, spec = fixture(n=29)
        rows, _, _ = analysis.build_tables(records, auxiliary, spec)
        row = selected(rows)
        self.assertEqual(row["status"], "insufficient_joint_support")
        self.assertEqual(row["n_joint_valid"], 29)
        self.assertIsNotNone(row["mean"])
        self.assertIsNone(row["p_value_two_sided"])

    def test_operational_gaps_duplicates_invalid_values_and_foreign_parents_are_rejected(self):
        records, auxiliary, spec = fixture(n=2)
        cases = []
        cases.append((records[:-1], auxiliary, "Missing study records"))
        cases.append((records + [records[0]], auxiliary, "Unexpected/duplicate/incomplete record"))
        cases.append((records, auxiliary[:-1], "Missing auxiliary records"))
        for changes in ({"parent_id": 920199}, {"status": "failed"}, {"metrics": {m: float("nan") for m in PRIMARY}}):
            altered = copy.deepcopy(records)
            altered[0].update(changes)
            cases.append((altered, auxiliary, "Invalid distance|Unexpected/duplicate/incomplete record"))
        for primary, aux, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                analysis.build_tables(primary, aux, spec)


if __name__ == "__main__":
    unittest.main()
