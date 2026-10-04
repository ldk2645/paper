import unittest

import numpy as np

from abm_jasss.governance import PendingResponse, ResponseController, episodes, trust_update


def controller(**kwargs):
    config = dict(n_topics=4, agenda_topics=(0, 1), threshold=.25,
                  strategy="hard", wait_observations=2, capacity=1, delay=3)
    config.update(kwargs)
    return ResponseController(**config)


def update(**kwargs):
    config = dict(trust=.5, baseline=.5, official_exposure=.25,
                  offagenda_exposure=.5, alignment=.5, response_effect=0,
                  rate=.2, rule="exposure", official_gain=1,
                  offagenda_penalty=1, response_gain=1, alignment_gain=1)
    config.update(kwargs)
    return trust_update(**config)


class GovernanceTests(unittest.TestCase):
    def test_capacity_delay_and_no_pending_duplicate(self):
        policy = controller()
        rng = np.random.default_rng(2)
        self.assertEqual(policy.schedule(0, [.4, .3, .2, .1], rng),
                         [PendingResponse(0, 0, 3, .4)])
        self.assertEqual(policy.schedule(1, [.4, .3, .2, .1], rng),
                         [PendingResponse(1, 1, 4, .3)])
        self.assertEqual(policy.schedule(2, [.4, .3, .2, .1], rng), [])
        self.assertEqual(policy.due(2), [])
        self.assertEqual(policy.due(3), [PendingResponse(0, 0, 3, .4)])
        self.assertEqual(policy.due(3), [])
        self.assertEqual(policy.schedule(3, [.4, .3, .2, .1], rng),
                         [PendingResponse(0, 3, 6, .4)])
        self.assertEqual([x.topic for x in policy.due(9)], [1, 0])

    def test_due_same_round_sorted_by_topic(self):
        policy = controller(capacity=3, threshold=.1)
        policy.schedule(0, [.2, .3, .4, .1], np.random.default_rng(1))
        self.assertEqual([x.topic for x in policy.due(3)], [0, 1, 2])

    def test_selective_and_strict_threshold(self):
        rng = np.random.default_rng(2)
        signal = [.25, .3, .4, .05]
        self.assertEqual([x.topic for x in controller().schedule(0, signal, rng)], [2])
        self.assertEqual([x.topic for x in controller(strategy="selective").schedule(0, signal, rng)], [1])
        self.assertEqual(controller(strategy="selective", agenda_topics=()).schedule(0, signal, rng), [])

    def test_wait_counts_monitoring_observations_and_resets_at_threshold(self):
        policy = controller(strategy="wait")
        rng = np.random.default_rng(2)
        self.assertEqual(policy.schedule(0, [.4, .2, .2, .2], rng), [])
        policy.due(1)
        policy.due(9)
        np.testing.assert_array_equal(policy.streak, [1, 0, 0, 0])
        self.assertEqual(policy.schedule(10, [.25, .25, .25, .25], rng), [])
        self.assertEqual(policy.schedule(20, [.4, .2, .2, .2], rng), [])
        self.assertEqual(policy.schedule(30, [.4, .2, .2, .2], rng),
                         [PendingResponse(0, 30, 33, .4)])

    def test_random_ties_cover_all_labels_and_leave_unequal_scores_ordered(self):
        rng = np.random.default_rng(41)
        counts = np.zeros(4, dtype=int)
        for _ in range(2000):
            plans = controller(threshold=.2).schedule(0, [.25] * 4, rng)
            counts[plans[0].topic] += 1
        self.assertTrue(((counts > 400) & (counts < 600)).all(), counts)
        policy = controller(threshold=.1, capacity=2)
        plans = policy.schedule(0, [.25000001, .25, .2, .1], rng)
        self.assertEqual([x.topic for x in plans], [0, 1])

    def test_trust_exposure_formula_by_hand_and_disabled_penalty(self):
        expected_target = 1 / (1 + np.exp(.5))
        self.assertAlmostEqual(update(), .5 + .2 * (expected_target - .5))
        self.assertEqual(update(offagenda_penalty=0), .5)
        self.assertGreater(update(offagenda_penalty=0, official_exposure=.75), .5)
        self.assertLess(update(offagenda_penalty=0, response_effect=-.5), .5)

    def test_frozen_trust_and_alternative_rules_bounded(self):
        old = np.array([0, .2, .8, 1])
        for rule in ("exposure", "alignment"):
            np.testing.assert_array_equal(update(trust=old, baseline=old, rate=0, rule=rule), old)
            result = update(trust=old, baseline=old, rate=1, rule=rule,
                            response_effect=np.array([-1000, 1000, -1000, 1000]))
            self.assertTrue(np.isfinite(result).all())
            self.assertTrue(((result >= 0) & (result <= 1)).all())
        self.assertEqual(update(rule="alignment"), .5)
        self.assertGreater(update(rule="alignment", alignment=1), .5)
        self.assertLess(update(rule="alignment", alignment=0), .5)
        self.assertEqual(update(rule="alignment", official_exposure=1, offagenda_exposure=1), .5)

    def test_episodes_include_terminal_censoring_and_strict_threshold(self):
        rows = [{"step": k, "value": value} for k, value in enumerate([.5, .6, .8, .5, .7, .9])]
        self.assertEqual(episodes(rows, "value", .5), [
            dict(start_step=1, end_step=2, duration=2, peak_value=.8, right_censored=False),
            dict(start_step=4, end_step=5, duration=2, peak_value=.9, right_censored=True)])
        self.assertEqual(episodes([], "value", .5), [])
        self.assertEqual(episodes([dict(step=0, value=.6)], "value", .5), [
            dict(start_step=0, end_step=0, duration=1, peak_value=.6, right_censored=True)])

    def test_invalid_config_and_incomplete_episode_data_rejected(self):
        for kwargs in ({"delay": 0}, {"capacity": 0}, {"threshold": float("nan")},
                       {"agenda_topics": (4,)}, {"strategy": "unknown"}, {"n_topics": True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                controller(**kwargs)
        with self.assertRaises(ValueError):
            episodes([dict(step=0, value=.8), dict(step=2, value=.8)], "value", .5)
        with self.assertRaises(ValueError):
            controller().schedule(0, [.2, .3, .4, float("nan")], np.random.default_rng(1))
        with self.assertRaises(ValueError):
            update(rate=1.1)


if __name__ == "__main__":
    unittest.main()
