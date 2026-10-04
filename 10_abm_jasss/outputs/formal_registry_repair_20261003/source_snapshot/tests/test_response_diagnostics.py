from copy import deepcopy
import unittest

from abm_jasss.response_diagnostics import response_target_diagnostics


def example():
    config = {"active_arm": "platform", "n_topics": 3, "steps": 4}
    preferences = [[.7, .2, .1], [.4, .4, .2], [.1, .7, .2], [.2, .7, .1]]
    rows = []
    for step, preference in enumerate(preferences):
        row = {"step": step}
        for prefix, vector in (("truth", preference), ("attention", [.2, .7, .1]),
                               ("estimate_platform", [.6, .3, .1])):
            row.update({f"{prefix}_{k}": value for k, value in enumerate(vector)})
        rows.append(row)
    events = []
    for topic, signal in ((0, .6), (1, .3)):
        base = dict(topic=topic, trigger_step=0, due_step=2, signal_value=signal)
        events.append(dict(base, kind="response_scheduled", step=0))
        events.append(dict(base, kind="response_executed", step=2))
    return rows, events, config


class ResponseDiagnosticsTests(unittest.TestCase):
    def test_cohort_time_alignment_and_three_distinct_distances_by_hand(self):
        rows, events, config = example()
        output = response_target_diagnostics(rows, events, config, [])
        self.assertEqual(output["pending_cohorts"], [])
        cohort, = output["executed_cohorts"]
        self.assertEqual(cohort["target_distribution"], [.5, .5, 0])
        self.assertEqual((cohort["trigger_step"], cohort["due_step"], cohort["step"], cohort["n_actions"]), (0, 2, 2, 2))
        for key, value in (
            ("response_target_mismatch_at_trigger", .3),
            ("response_target_mismatch_at_execution", .4),
            ("signed_mismatch_change", .1),
            ("preference_drift_between_trigger_and_execution", .6),
            ("representation_error_at_trigger", .5),
            ("sensing_error_at_trigger", .1),
            ("signal_estimate_distance_at_trigger", .4),
        ):
            self.assertAlmostEqual(cohort[key], value)
        self.assertEqual(cohort["public_preference_at_trigger"], [.7, .2, .1])
        self.assertEqual(cohort["public_preference_at_execution"], [.1, .7, .2])

    def test_different_due_times_are_separate_and_change_can_be_negative(self):
        rows, events, config = example()
        for event in events:
            if event["topic"] == 1:
                event["due_step"] = 3
                if event["kind"] == "response_executed":
                    event["step"] = 3
        first, second = response_target_diagnostics(rows, events, config)["executed_cohorts"]
        self.assertEqual(first["target_distribution"], [1, 0, 0])
        self.assertEqual(second["target_distribution"], [0, 1, 0])
        self.assertAlmostEqual(first["response_target_mismatch_at_trigger"], 1 - rows[0]["truth_0"])
        self.assertAlmostEqual(second["signed_mismatch_change"], -.5)

    def test_no_response_has_no_error_value(self):
        rows, _, config = example()
        output = response_target_diagnostics(rows, [{"kind": "routine_publication", "step": 0, "topic": 0}], config, [])
        self.assertEqual(output, {"executed_cohorts": [], "pending_cohorts": []})

    def test_terminal_pending_counts_are_separate_from_executed_mismatch(self):
        rows, events, config = example()
        pending = dict(topic=2, trigger_step=3, due_step=6, signal_value=.1)
        events.append(dict(pending, kind="response_scheduled", step=3))
        output = response_target_diagnostics(rows, events, config, [pending])
        self.assertEqual(len(output["executed_cohorts"]), 1)
        self.assertEqual(output["pending_cohorts"], [
            dict(step=3, trigger_step=3, due_step=6, n_actions=1, right_censored=True)])
        self.assertEqual(output, response_target_diagnostics(rows, events, config))

    def test_csv_rows_and_embedded_event_references(self):
        rows, events, config = example()
        events[0].update(target_preference_at_trigger=.7, target_attention_at_trigger=.2, target_estimation_error=.1)
        events[1]["target_preference_at_execution"] = .1
        numeric = response_target_diagnostics(rows, events, config)
        csv_rows = [{key: str(value) for key, value in row.items()} for row in rows]
        self.assertEqual(numeric, response_target_diagnostics(csv_rows, events, config))
        events[1]["target_preference_at_execution"] = .7
        with self.assertRaisesRegex(ValueError, "disagrees"):
            response_target_diagnostics(rows, events, config)
        self.assertEqual(numeric, response_target_diagnostics(rows, events, config, validate_references=False))

    def test_malformed_or_missing_event_pairs_are_rejected(self):
        rows, events, config = example()
        cases = []
        duplicate = deepcopy(events)
        duplicate.append(deepcopy(events[0]))
        cases.append(duplicate)
        cases.append(events[1:])
        cases.append([events[0], events[2], events[3]])
        wrong_time = deepcopy(events)
        wrong_time[1]["step"] = 1
        cases.append(wrong_time)
        wrong_signal = deepcopy(events)
        wrong_signal[0]["signal_value"] = .7
        cases.append(wrong_signal)
        overlap = deepcopy(events)
        overlap.append(dict(kind="response_scheduled", step=1, trigger_step=1, due_step=4, topic=0, signal_value=.6))
        cases.append(overlap)
        for case in cases:
            with self.subTest(events=case), self.assertRaises(ValueError):
                response_target_diagnostics(rows, case, config)
        with self.assertRaises(ValueError):
            response_target_diagnostics(rows, events, config, [dict(topic=0, trigger_step=0, due_step=2, signal_value=.6)])

    def test_trajectory_gaps_and_bad_distributions_are_rejected(self):
        rows, events, config = example()
        missing = rows[:2] + rows[3:]
        duplicate = rows[:2] + [rows[1]] + rows[3:]
        invalid = deepcopy(rows)
        invalid[0]["truth_0"] = .8
        for case in (missing, duplicate, invalid):
            with self.subTest(rows=case), self.assertRaises(ValueError):
                response_target_diagnostics(case, events, config)


if __name__ == "__main__":
    unittest.main()
