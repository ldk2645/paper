"""Small E3 acceptance checks; fixed timing contrasts are not adaptive policies."""
import copy
from dataclasses import replace
import json
import unittest

from abm_jasss.research_config import ResearchConfig
from abm_jasss.research_replay import (ControlledReplayWorld, FixedReplayPlan, make_replay_worlds,
                                     rebuild_replay_diagnostics, replay_diagnostics)
from abm_jasss.research_world import ResearchWorld, canonical_hash


def config(**changes):
    values = dict(n_agents=10, n_topics=2, steps=8, final_window=3,
        population_weights=(1., 1.), agenda_topics=(0,), advantaged_topic=1,
        initial_items=6, arrivals_per_step=2, attention_budget=2,
        emotion_mean=.8, emotion_advantage=0., official_emotion_mean=.8,
        interaction_mean=1., interaction_sd=0., trust_feedback_strength=0.,
        pref_info=True, sampling_rate=0., survey_size=10, survey_interval=1,
        observation_window=2, update_frequency=1, inference_grid=4, reference_agents=2,
        response_threshold=0., response_capacity=2, government_delay=0,
        routine_publication_interval=2, completion_followup=2)
    values.update(changes)
    return ResearchConfig(**values)


class ReplayTests(unittest.TestCase):
    def donor(self, **changes):
        return ResearchWorld(config(**changes), 107).run()

    def test_fixed_triggers_targets_parameters_and_counts_survive_topic_overlap(self):
        donor = self.donor()
        worlds = make_replay_worlds(donor, (0, 1, 3))
        fields = ("event_id", "trigger_step", "topic", "action_parameters")
        expected = [{key: event[key] for key in fields} for event in donor.events]
        self.assertTrue(expected)
        for delay, world in worlds.items():
            world.run()
            self.assertEqual([{key: event[key] for key in fields} for event in world.events], expected)
            for event in world.events:
                self.assertEqual(event["due_step"], event["trigger_step"] + delay)
                self.assertEqual(event["decision_mode"], "controlled_fixed_plan")
                self.assertEqual(event["information_ref"]["kind"], "controlled_fixed_plan")
                self.assertEqual(event["donor_information_ref"],
                    next(item for item in donor.events if item["event_id"] == event["event_id"])["information_ref"])
            self.assertEqual(replay_diagnostics(world)["triggered_count"], len(donor.events))
        slow = worlds[3]
        self.assertGreater(max(row["pending_count"] for row in slow.trajectory), slow.config.n_topics)
        zero = worlds[0]
        self.assertTrue(all(event["execution_step"] == event["trigger_step"] for event in zero.events))
        self.assertEqual(zero.supply_log, slow.supply_log)
        routine = lambda world: [item for item in world.publication_log if item["source"] == 1]
        self.assertEqual(routine(zero), routine(slow))

    def test_responses_keep_stable_identity_and_content_across_execution_times(self):
        worlds = make_replay_worlds(self.donor(), (0, 3))
        for world in worlds.values():
            world.run()
            items = world.supply_log + world.publication_log
            self.assertEqual(len(items), len({item["item_id"] for item in items}))
        replies = lambda world: {item["item_id"]: item for item in world.publication_log if item["source"] == 2}
        fast, slow = replies(worlds[0]), replies(worlds[3])
        self.assertTrue(slow)
        for item_id, item in slow.items():
            self.assertEqual(item["born"], fast[item_id]["born"] + 3)
            self.assertEqual({key: value for key, value in item.items() if key != "born"},
                             {key: value for key, value in fast[item_id].items() if key != "born"})

    def test_receiver_sensing_can_diverge_without_replanning_or_donor_future_inputs(self):
        donor = self.donor()
        left = make_replay_worlds(donor, (1,))[1]
        right = make_replay_worlds(donor, (1,))[1]
        right.preferences[:] = (1., 0.)
        left.run()
        right.run()
        self.assertNotEqual(left.government_estimates, right.government_estimates)
        self.assertEqual([(e["event_id"], e["topic"], e["due_step"]) for e in left.events],
                         [(e["event_id"], e["topic"], e["due_step"]) for e in right.events])
        for info in right.information_log:
            self.assertNotIn("donor", json.dumps(info))
            if info["survey"] is not None:
                self.assertLess(info["survey"]["measured_at"], info["now"])
                self.assertLessEqual(info["survey"]["available_at"], info["now"])
        self.assertTrue(all(event["P_trigger"] == [1., 0.] for event in right.events[:2]))

    def test_terminal_unexecuted_plans_remain_right_censored_and_rebuild_exactly(self):
        world = make_replay_worlds(self.donor(), (20,))[20].run()
        before = world.snapshot()
        diagnostic = replay_diagnostics(world)
        self.assertEqual(diagnostic, rebuild_replay_diagnostics(world.trajectory, world.events,
            world.replay_plan.to_dict(), 20, world.config.steps))
        self.assertEqual(diagnostic["right_censored_count"], len(world.events))
        self.assertEqual(diagnostic["execution_count"], 0)
        self.assertTrue(all(item["status"] == "right_censored" for item in diagnostic["event_statuses"]))
        self.assertTrue(all(event["execution_step"] is None and event["P_execution"] is None
                            for event in world.events))
        self.assertEqual(world.snapshot(), before)
        edited = copy.deepcopy(world.events)
        edited.pop()
        with self.assertRaisesRegex(ValueError, "conserve"):
            rebuild_replay_diagnostics(world.trajectory, edited, world.replay_plan.to_dict(), 20, 8)

    def test_json_snapshot_resume_with_overlapping_pending_is_exact_and_isolated(self):
        original = make_replay_worlds(self.donor(), (3,))[3].run(4)
        snapshot = json.loads(json.dumps(original.snapshot()))
        restored = ControlledReplayWorld.from_snapshot(snapshot)
        self.assertEqual(restored.snapshot(), original.snapshot())
        self.assertEqual(replay_diagnostics(restored)["right_censored_count"], 0)
        original.run()
        restored.run()
        self.assertEqual(original.snapshot(), restored.snapshot())
        restored.events[0]["donor_information_ref"]["information_hash"] = "edited"
        self.assertNotEqual(restored.events, original.events)
        with self.assertRaisesRegex(ValueError, "ControlledReplayWorld"):
            ResearchWorld.from_snapshot(snapshot)
        adaptive = ResearchWorld(config(), 107).run(2)
        self.assertEqual(ResearchWorld.from_snapshot(adaptive.snapshot()).snapshot(), adaptive.snapshot())
        with self.assertRaisesRegex(ValueError, "controlled replay snapshot"):
            ControlledReplayWorld.from_snapshot(adaptive.snapshot())
        with self.assertRaisesRegex(ValueError, "fork"):
            original.fork("adaptive")

    def test_modified_replay_queue_cannot_silently_drop_overlapping_pending(self):
        world = make_replay_worlds(self.donor(), (3,))[3].run(3)
        snapshot = world.snapshot()
        snapshot["state"]["queue"]["pending"].pop()
        snapshot["state_hash"] = canonical_hash(snapshot["state"])
        with self.assertRaisesRegex(ValueError, "queue disagrees"):
            ControlledReplayWorld.from_snapshot(snapshot)

    def test_plan_is_immutable_and_rejects_illegal_or_partial_donors(self):
        donor = self.donor()
        plan = FixedReplayPlan.from_donor(donor)
        edited = plan.to_dict()
        edited["events"].clear()
        self.assertEqual(len(plan.to_dict()["events"]), len(donor.events))
        self.assertEqual(FixedReplayPlan.from_dict(plan.to_dict()), plan)
        illegal = copy.deepcopy(donor)
        illegal.events[0]["signal_value"] = .123
        with self.assertRaisesRegex(ValueError, "legal government decisions"):
            FixedReplayPlan.from_donor(illegal)
        illegal = copy.deepcopy(donor)
        illegal.information_log[1]["survey"]["available_at"] = 2
        with self.assertRaises(ValueError):
            FixedReplayPlan.from_donor(illegal)
        with self.assertRaisesRegex(ValueError, "complete"):
            FixedReplayPlan.from_donor(ResearchWorld(config(), 107).run(3))

    def test_public_signal_and_rule_information_donors_reconstruct_legally(self):
        for pref_info, rule_info in ((False, False), (False, True), (True, True)):
            with self.subTest(pref_info=pref_info, rule_info=rule_info):
                donor = self.donor(pref_info=pref_info, rule_info=rule_info,
                                   sampling_rate=1., government_delay=1)
                self.assertTrue(donor.events)
                replay = make_replay_worlds(donor, (0,))[0].run()
                self.assertEqual(replay_diagnostics(replay)["triggered_count"], len(donor.events))
                for info in replay.information_log:
                    if info["public_packet"] is not None:
                        self.assertLess(info["public_packet"]["window_end"], info["now"])
                        self.assertLessEqual(info["public_packet"]["available_at"], info["now"])

    def test_empty_plan_and_invalid_delay_configuration(self):
        donor = self.donor(response_enabled=False)
        world = make_replay_worlds(donor, (0,))[0].run()
        self.assertEqual(world.events, [])
        self.assertEqual(replay_diagnostics(world)["fixed_plan_count"], 0)
        for delays in ((), (1, 1), (-1,), (True,)):
            with self.subTest(delays=delays), self.assertRaises(ValueError):
                make_replay_worlds(donor, delays)
        with self.assertRaisesRegex(ValueError, "preserve"):
            ControlledReplayWorld(replace(donor.config, alpha=.1), donor.seed,
                                  FixedReplayPlan.from_donor(donor), 0)


if __name__ == "__main__":
    unittest.main()
