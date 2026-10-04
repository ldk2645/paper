"""Constructed access, numerical-use, timing and restart tests for sensing."""
from dataclasses import FrozenInstanceError, replace
import json
import unittest

import numpy as np

from abm_jasss.government_sensing import (
    GovernmentInformation, GovernmentSensing, PublicContent, RuleDisclosure,
    SensingSettings, SurveyReport,
)
from abm_jasss.public_signals import PublicSignalPublisher


def packet(counts=(8, 2), window=1):
    publisher = PublicSignalPublisher(len(counts), window, 0)
    return publisher.publish(0, counts, np.random.default_rng(42))[1]


def catalog():
    return (PublicContent("a", 0, .5, 100., False, 0),
            PublicContent("b", 0, .5, 90., False, 0),
            PublicContent("c", 1, .5, .1, False, 0),
            PublicContent("d", 1, .5, .1, False, 0))


def estimator(**kwargs):
    values = {"n_topics": 2, "grid_resolution": 10, "reference_agents": 4,
              "opaque_attention_budget": 1}
    values.update(kwargs)
    return GovernmentSensing(SensingSettings(**values))


def information(now=1, public=None, survey=None, rule=None, with_catalog=True):
    observed = packet() if public is None else public
    return GovernmentInformation(now, observed, survey, rule,
                                 catalog() if with_catalog else (),
                                 observed.window_end if with_catalog else None)


class GovernmentSensingTests(unittest.TestCase):
    def test_frozen_whitelist_and_no_world_or_hidden_state_inputs(self):
        info = information()
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            info.now = 99
        self.assertFalse(hasattr(info, "__dict__"))
        with self.assertRaises(TypeError):
            GovernmentInformation(now=1, P_true=(.2, .8))
        with self.assertRaises(TypeError):
            PublicContent("a", 0, .5, 1., False, 0, preferences=(.2, .8))
        with self.assertRaises(TypeError):
            estimator().update({"world": object(), "public_packet": packet()})
        # Hidden states are deliberately not expressible at the update boundary.
        hidden_world_a = {"P": (.1, .9), "E": (.7, .3)}
        hidden_world_b = {"P": (.9, .1), "E": (.2, .8)}
        self.assertNotEqual(hidden_world_a, hidden_world_b)
        self.assertEqual(estimator().update(info), estimator().update(info))

    def test_four_cells_enforce_extra_information_permissions(self):
        survey = SurveyReport("survey", 0, 1, 5, (.3, .7))
        rule = RuleDisclosure("actual", 0, 0, .8, attention_budget=1)
        for pref_info, rule_info in ((False, False), (True, False), (False, True), (True, True)):
            sensing = estimator(pref_info=pref_info, rule_info=rule_info)
            info = information(survey=survey if pref_info else None, rule=rule if rule_info else None)
            result = sensing.update(info)
            self.assertTrue(result["updated"])
            self.assertEqual("survey.estimate" in result["consumed_fields"], pref_info)
            self.assertEqual("rule.alpha" in result["consumed_fields"], rule_info)
            if not pref_info:
                with self.assertRaises(PermissionError):
                    sensing.update(information(now=2, survey=survey))
            if not rule_info:
                with self.assertRaises(PermissionError):
                    sensing.update(information(now=2, rule=rule))

    def test_disclosure_enters_forward_model_and_preserves_numerical_budget(self):
        public = packet((10, 0))
        opaque = estimator()
        transparent = estimator(rule_info=True)
        report_a = opaque.update(information(public=public))
        report_b = transparent.update(information(public=public,
            rule=RuleDisclosure("heat-only", 0, 0, 1., attention_budget=1)))
        self.assertNotEqual(opaque.estimate, transparent.estimate)
        # Different latent candidates may explain exactly the same public signal.
        # Requiring different fitted signals would wrongly reject that valid case.
        self.assertNotEqual(report_a["candidate_estimate"], report_b["candidate_estimate"])
        self.assertEqual(report_a["candidate_count"], report_b["candidate_count"])
        self.assertEqual(report_a["forward_evaluations"], report_b["forward_evaluations"])
        self.assertEqual(report_b["estimate_input_rule_version"], "heat-only")

    def test_redundant_rule_information_can_give_identical_estimate(self):
        settings = {"opaque_alpha": (.5, .5, .5)}
        opaque = estimator(**settings)
        transparent = estimator(rule_info=True, **settings)
        opaque.update(information())
        transparent.update(information(rule=RuleDisclosure("redundant", 0, 0, .5, attention_budget=1)))
        self.assertEqual(opaque.estimate, transparent.estimate)

    def test_packet_id_replacement_does_not_repeat_smoothing(self):
        sensing = estimator(smoothing=.5)
        first = packet()
        output = sensing.update(information(public=first))
        state_before = sensing.estimate
        repackaged = replace(first, packet_id="reissued-id")
        held = sensing.update(information(now=2, public=repackaged))
        self.assertEqual(sensing.estimate, state_before)
        self.assertEqual(held["reason"], "unchanged_evidence")
        self.assertFalse(held["updated"])
        self.assertEqual(held["available_packet_id"], "reissued-id")
        self.assertEqual(held["estimate_input_packet_id"], output["estimate_input_packet_id"])

    def test_rule_redelivery_does_not_repeat_smoothing(self):
        sensing = estimator(rule_info=True, smoothing=.5)
        rule = RuleDisclosure("same-rule", 0, 1, 0., attention_budget=1)
        first = sensing.update(information(rule=rule))
        self.assertTrue(first["updated"])
        self.assertNotEqual(sensing.estimate, (.5, .5))
        before = sensing.estimate
        held = sensing.update(information(now=2, rule=replace(rule, available_at=2)))
        self.assertFalse(held["updated"])
        self.assertEqual(held["reason"], "unchanged_evidence")
        self.assertEqual(sensing.estimate, before)
        self.assertEqual(held["estimate_updated_at"], first["estimate_updated_at"])
        # A changed rule still constitutes new evidence even for the same packet.
        changed = sensing.update(information(now=3,
            rule=replace(rule, version="changed-rule", alpha=1., available_at=3)))
        self.assertTrue(changed["updated"])
        self.assertEqual(changed["estimate_input_rule_version"], "changed-rule")
        self.assertNotEqual(sensing.estimate, before)

    def test_not_update_tick_keeps_actual_used_packet_separate(self):
        sensing = estimator(update_frequency=2)
        first = packet()
        early = sensing.update(information(now=1, public=first))
        self.assertFalse(early["updated"])
        self.assertIsNone(early["estimate_input_packet_id"])
        sensing.update(information(now=2, public=first))
        estimate = sensing.estimate
        publisher = PublicSignalPublisher(2, 1, 0)
        publisher.publish(0, (8, 2), np.random.default_rng(1))
        second = publisher.publish(1, (1, 9), np.random.default_rng(1))[1]
        held = sensing.update(GovernmentInformation(3, second))
        self.assertEqual(held["reason"], "not_update_tick")
        self.assertEqual(held["available_packet_id"], second.packet_id)
        self.assertEqual(held["estimate_input_packet_id"], first.packet_id)
        self.assertEqual(sensing.estimate, estimate)

    def test_future_packet_survey_rule_and_catalog_are_rejected(self):
        with self.assertRaises(ValueError):
            estimator().update(GovernmentInformation(0, packet()))
        with self.assertRaises(ValueError):
            estimator(pref_info=True).update(GovernmentInformation(1, survey=SurveyReport("s", 0, 2, 2, (.5, .5))))
        with self.assertRaises(ValueError):
            estimator(rule_info=True).update(GovernmentInformation(1, rule=RuleDisclosure("r", 2, 2, .4)))
        with self.assertRaises(ValueError):
            GovernmentInformation(1, packet(), public_catalog=catalog(), catalog_observed_at=1)
        with self.assertRaises(ValueError):
            estimator().update(GovernmentInformation(2, packet(), public_catalog=catalog(), catalog_observed_at=1))

    def test_no_observations_and_rule_only_remain_prior(self):
        sensing = estimator(rule_info=True)
        report = sensing.update(GovernmentInformation(0, rule=RuleDisclosure("r", 0, 0, .9)))
        self.assertEqual(report["reason"], "no_preference_observation")
        self.assertFalse(sensing.has_data)
        self.assertEqual(sensing.estimate, (.5, .5))
        empty = packet((0, 0))
        report = sensing.update(GovernmentInformation(1, empty))
        self.assertFalse(report["updated"])
        self.assertFalse(sensing.has_data)

    def test_survey_can_update_without_public_signal(self):
        sensing = estimator(pref_info=True, smoothing=.5)
        survey = SurveyReport("s", 0, 1, 4, (.8, .2))
        result = sensing.update(GovernmentInformation(1, survey=survey))
        self.assertTrue(sensing.has_data)
        self.assertTrue(result["updated"])
        self.assertIsNone(result["estimate_input_packet_id"])
        self.assertEqual(result["consumed_fields"], ["survey.estimate"])
        np.testing.assert_allclose(sensing.estimate, (.65, .35))
        held = sensing.update(GovernmentInformation(2, survey=replace(survey, report_id="reissued", available_at=2)))
        self.assertFalse(held["updated"])

    def test_rule_does_not_reinterpret_signal_before_its_effective_date(self):
        sensing = estimator(rule_info=True)
        report = sensing.update(information(now=2,
            rule=RuleDisclosure("new", 1, 1, 1., attention_budget=1)))
        self.assertFalse(report["rule_used"])
        self.assertEqual(report["rule_window_status"], "not_applicable_to_source_window")
        self.assertIsNone(report["estimate_input_rule_version"])

    def test_snapshot_roundtrip_json_and_branch_independence(self):
        sensing = estimator(pref_info=True, smoothing=.5)
        sensing.update(information(survey=SurveyReport("s", 0, 1, 5, (.4, .6))))
        snapshot = json.loads(json.dumps(sensing.snapshot()))
        restored = GovernmentSensing.from_snapshot(snapshot)
        self.assertEqual(sensing.snapshot(), restored.snapshot())
        info = information(now=2, survey=SurveyReport("s2", 1, 2, 5, (.1, .9)))
        self.assertEqual(sensing.update(info), restored.update(info))
        restored.update(information(now=3, survey=SurveyReport("s3", 2, 3, 5, (1., 0.))))
        self.assertNotEqual(sensing.estimate, restored.estimate)
        self.assertEqual(snapshot["state"]["estimate_updated_at"], 1)
        with self.assertRaises(ValueError):
            restored.update(information(now=1))

    def test_candidate_reference_means_and_output_are_normalized(self):
        sensing = estimator(n_topics=4, grid_resolution=4)
        np.testing.assert_allclose(sensing._reference_preferences.mean(axis=1), sensing._candidates, atol=1e-15)
        np.testing.assert_allclose(sensing._reference_preferences.sum(axis=2), 1.)
        self.assertTrue((sensing._reference_preferences >= 0).all())
        report = sensing.update(GovernmentInformation(1, packet((1, 2, 3, 4))))
        self.assertAlmostEqual(sum(sensing.estimate), 1.)
        self.assertTrue(all(np.isfinite(value) and value >= 0 for value in sensing.estimate))
        self.assertEqual(report["catalog_mode"], "neutral_fallback")

    def test_zero_expected_activity_is_not_manufactured_into_public_evidence(self):
        sensing = estimator(reference_interaction_mean=0., reference_interaction_sd=0.)
        report = sensing.update(information())
        self.assertFalse(report["updated"])
        self.assertEqual(report["reason"], "no_predictive_support")
        self.assertFalse(sensing.has_data)

    def test_invalid_mutable_information_and_settings_are_rejected(self):
        with self.assertRaises(ValueError):
            SurveyReport("s", 0, 1, 2, [.4, .6])
        with self.assertRaises(ValueError):
            SurveyReport("s", 0, 0, 2, (.4, .6))
        with self.assertRaises(ValueError):
            GovernmentInformation(1, packet(), public_catalog=list(catalog()), catalog_observed_at=0)
        with self.assertRaises(ValueError):
            SensingSettings(2, opaque_alpha=[.2, .8])
        with self.assertRaises(ValueError):
            SensingSettings(2, smoothing=0.)
        with self.assertRaises(ValueError):
            SensingSettings(30, grid_resolution=10)


if __name__ == "__main__":
    unittest.main()
