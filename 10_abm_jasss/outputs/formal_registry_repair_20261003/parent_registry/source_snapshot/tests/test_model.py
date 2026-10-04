from dataclasses import replace
import unittest

import numpy as np

from abm_jasss.cli import aggregate
from abm_jasss.model import ARMS, Config, choose_items, normalize, simulate, summarize, tv, update_preferences


def small(**kwargs):
    return replace(Config(n_agents=20, steps=30, final_window=10, survey_size=5, initial_items=8), **kwargs)


class ModelTests(unittest.TestCase):
    def test_invalid_inputs_fail_early(self):
        for kwargs in ({"alpha": -1}, {"survey_size": 21}, {"final_window": 31}, {"ranking": "bad"},
                       {"emotion_advantage": 0.7}, {"observation_delay": -1}, {"supply_weights": (1, -1, 1, 1)},
                       {"n_agents": True}, {"government_delay": 0}, {"temperature": float("nan")}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                small(**kwargs)

    def test_zero_count_prior_and_known_tv(self):
        np.testing.assert_allclose(normalize([0, 0, 0, 0]), [.25] * 4)
        self.assertAlmostEqual(tv([1, 0], [0, 1]), 1)
        with self.assertRaises(ValueError):
            normalize([1, -1])

    def test_preference_update_by_hand_and_tie_reset(self):
        p = np.array([[.5, .5], [.2, .8]])
        q, dominant, streak = update_preferences(p, np.array([[3, 1], [2, 2]]), np.array([0, 1]), np.array([3, 3]), .1, 4)
        np.testing.assert_allclose(q, [[.55, .45], [.2, .8]])
        np.testing.assert_array_equal(dominant, [0, -1])
        np.testing.assert_array_equal(streak, [4, 0])

    def test_topk_uses_scores_and_no_duplicate_selection(self):
        scores = np.array([[.1, .8, .3, .9], [.2, .6, .7, .1]])
        chosen = choose_items(scores, 2, "topk", .1, np.random.default_rng(1))
        np.testing.assert_array_equal(np.sort(chosen, axis=1), [[1, 3], [1, 2]])
        chosen = choose_items(scores, 4, "softmax", .1, np.random.default_rng(1))
        for row in chosen:
            self.assertEqual(len(set(row)), 4)

    def test_exact_ties_do_not_favor_low_indices(self):
        scores = np.ones((1, 4))
        rng = np.random.default_rng(7)
        selections = [choose_items(scores, 1, "topk", .1, rng)[0, 0] for _ in range(1000)]
        counts = np.bincount(selections, minlength=4)
        self.assertTrue(((counts > 190) & (counts < 310)).all())

    def test_determinism_and_different_seed(self):
        first = simulate(small(), 123)
        self.assertEqual(first, simulate(small(), 123))
        self.assertNotEqual(first["rows"], simulate(small(), 124)["rows"])

    def test_all_distributions_and_oracle(self):
        for ranking in ("topk", "softmax"):
            result = simulate(small(ranking=ranking, drift_rate=.1), 11)
            for row in result["rows"]:
                for prefix in ("truth", "attention", *(f"estimate_{a}" for a in ARMS)):
                    vector = np.array([row[f"{prefix}_{k}"] for k in range(4)])
                    self.assertTrue((vector >= 0).all())
                    self.assertAlmostEqual(vector.sum(), 1)
                self.assertLess(row["error_oracle"], 1e-12)
                for arm in ARMS:
                    self.assertTrue(0 <= row[f"error_{arm}"] <= 1)

    def test_survey_does_not_change_world_without_feedback(self):
        a = simulate(small(survey_size=3, fusion_weight=.1), 8)["rows"]
        b = simulate(small(survey_size=18, fusion_weight=.9), 8)["rows"]
        for x, y in zip(a, b):
            for key in ("interactions", "pool_size", "attention_error", "preference_change", "error_platform"):
                self.assertEqual(x[key], y[key])
            for k in range(4):
                self.assertEqual(x[f"truth_{k}"], y[f"truth_{k}"])

    def test_full_census_matches_oracle_when_current(self):
        result = simulate(small(survey_size=20, observation_interval=1, drift_rate=.1), 99)
        self.assertTrue(all(r["error_survey"] < 1e-12 for r in result["rows"]))

    def test_observation_delay_prior_and_update(self):
        result = simulate(small(observation_delay=3, observation_interval=4), 33)
        for row in result["rows"][:3]:
            self.assertEqual(row["observation_updated"], 0)
            self.assertEqual([row[f"estimate_survey_{k}"] for k in range(4)], [.25] * 4)
        self.assertEqual(result["rows"][3]["observation_updated"], 1)
        self.assertEqual(result["rows"][7]["observation_updated"], 1)

    def test_no_interactions_and_small_pool(self):
        result = simulate(small(initial_items=1, arrivals_per_step=1, interaction_mean=0, interaction_sd=0, signal="interaction"), 1)
        self.assertTrue(all(r["interactions"] == 0 for r in result["rows"]))
        self.assertTrue(all(r["pool_size"] <= 2 for r in result["rows"]))
        self.assertTrue(all(r["estimate_platform_0"] == .25 for r in result["rows"]))

    def test_fixed_preferences_and_feedback_summary(self):
        result = simulate(small(government_policy="communicate", active_arm="survey"), 7)
        self.assertTrue(all(r["preference_change"] == 0 for r in result["rows"]))
        self.assertEqual([r["arm"] for r in summarize(result)], ["survey"])
        self.assertEqual(sum(r["official_arrivals"] for r in result["rows"]), 3)
        self.assertEqual(result["rows"][3]["official_arrivals"], 1)
        self.assertTrue(all(r["official_arrivals"] == 0 for r in result["rows"][:3]))

    def test_grace_period_keeps_unpopular_items_for_specified_rounds(self):
        result = simulate(small(initial_items=1, arrivals_per_step=1, interaction_mean=0,
                                interaction_sd=0, cold_start_rounds=3), 1)
        self.assertEqual([r["pool_size"] for r in result["rows"][:5]], [2, 3, 4, 3, 3])

    def test_biased_noisy_survey_is_valid_but_does_not_change_world(self):
        base = simulate(small(), 42)
        noisy = simulate(small(survey_noise_sd=.5, survey_selection_bias=5), 42)
        self.assertNotEqual([r["error_survey"] for r in base["rows"]], [r["error_survey"] for r in noisy["rows"]])
        for x, y in zip(base["rows"], noisy["rows"]):
            self.assertEqual(x["attention_error"], y["attention_error"])
            self.assertAlmostEqual(sum(y[f"estimate_survey_{k}"] for k in range(4)), 1)

    def test_skewed_population_and_uniform_baseline_are_recorded(self):
        result = simulate(small(population_weights=(.8, .1, .05, .05)), 42)
        first = result["rows"][0]
        self.assertGreater(first["truth_0"], .6)
        self.assertGreater(first["uniform_prior_error"], .3)
        self.assertIn("uniform_prior_error", summarize(result)[0])

    def test_bootstrap_uses_seed_pairs_not_row_order(self):
        rows = [{"alpha": .5, "arm": arm, "seed": seed, "mean_error": value}
                for seed in range(4) for arm, value in (("platform", seed / 10 + .2), ("survey", seed / 10 + .1))]
        grouped, contrasts = aggregate(rows[::-1])
        self.assertEqual(contrasts[0]["n_pairs"], 4)
        self.assertAlmostEqual(contrasts[0]["mean_difference"], -.1)
        self.assertAlmostEqual(contrasts[0]["ci_low"], -.1)
        self.assertAlmostEqual(contrasts[0]["ci_high"], -.1)
        self.assertEqual(grouped, aggregate(rows)[0])


if __name__ == "__main__":
    unittest.main()
