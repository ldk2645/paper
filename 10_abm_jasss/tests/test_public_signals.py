import copy
from dataclasses import FrozenInstanceError, replace
import json
import unittest

import numpy as np

from abm_jasss.public_signals import ObservationPacket, PublicSignalPublisher, PublicTick


class FixedNoise:
    def __init__(self, values):
        self.values = values
        self.calls = 0

    def normal(self, mean, sd, size):
        self.calls += 1
        return self.values


class PublicSignalTests(unittest.TestCase):
    def test_count_pooled_window_weights_and_delivery(self):
        publisher = PublicSignalPublisher(2, window=3, delay=2)
        first, packet = publisher.publish(0, [1, 3], None)
        self.assertEqual(first.signal, (.25, .75))
        self.assertEqual(packet.available_at, 3)
        self.assertEqual(packet.window_start, -2)
        self.assertTrue(packet.warm_up)
        self.assertEqual(packet.coverage, 1 / 3)
        publisher.publish(1, [0, 0], None)
        _, packet = publisher.publish(2, [6, 0], None)
        self.assertEqual(packet.valid_steps, (0, 2))
        self.assertEqual(packet.missing_steps, (1,))
        self.assertEqual(packet.counts, (7, 3))
        self.assertEqual(packet.signal, (.7, .3))
        self.assertEqual(packet.weights, (.4, .6))
        self.assertEqual(packet.tick_denominators, (4, 6))
        self.assertEqual(packet.coverage, 2 / 3)
        self.assertFalse(packet.warm_up)
        self.assertEqual(packet.available_at, 5)
        _, packet = publisher.publish(3, [2, 2], None)
        self.assertEqual(packet.valid_steps, (2, 3))
        self.assertEqual(packet.signal, (.8, .2))

    def test_missing_and_raw_zero_do_not_create_noise_evidence(self):
        publisher = PublicSignalPublisher(3, window=2, delay=0, noise_sd=100)
        rng = FixedNoise([100, 100, 100])
        tick, packet = publisher.publish(0, None, rng)
        self.assertEqual(tick.status, "no_panel")
        self.assertIsNone(tick.raw_counts)
        self.assertIsNone(packet.signal)
        self.assertEqual(packet.available_at, 1)
        tick, packet = publisher.publish(1, [0, 0, 0], rng)
        self.assertEqual(tick.status, "no_interactions")
        self.assertEqual(tick.denominator, 0)
        self.assertIsNone(tick.signal)
        self.assertIsNone(packet.signal)
        self.assertEqual(packet.weights, ())
        self.assertEqual(packet.missing_steps, (0, 1))
        self.assertEqual(rng.calls, 0)

    def test_noise_truncation_and_complete_erasure(self):
        publisher = PublicSignalPublisher(2, 1, 0, noise_sd=2)
        tick, _ = publisher.publish(0, [1, 3], FixedNoise([-4, 2]))
        self.assertEqual(tick.public_counts, (0, 5))
        self.assertEqual(tick.signal, (0, 1))
        tick, packet = publisher.publish(1, [1, 3], FixedNoise([-4, -4]))
        self.assertEqual(tick.status, "noise_erased")
        self.assertEqual(tick.public_counts, (0, 0))
        self.assertIsNone(tick.signal)
        self.assertIsNone(packet.signal)

    def test_repackaging_same_evidence_preserves_signature_until_it_expires(self):
        publisher = PublicSignalPublisher(2, 3, 0)
        _, first = publisher.publish(0, [2, 1], None)
        _, second = publisher.publish(1, [0, 0], None)
        _, third = publisher.publish(2, None, None)
        _, empty = publisher.publish(3, None, None)
        self.assertNotEqual(first.packet_id, second.packet_id)
        self.assertEqual(first.evidence_signature, second.evidence_signature)
        self.assertEqual(second.evidence_signature, third.evidence_signature)
        self.assertNotEqual(third.evidence_signature, empty.evidence_signature)
        self.assertEqual(replace(first, packet_id="repackaged").evidence_signature,
                         first.evidence_signature)
        # Equal shares at a different source tick are distinct evidence.
        _, newest = publisher.publish(4, [2, 1], None)
        self.assertNotEqual(first.evidence_signature, newest.evidence_signature)

    def test_immutable_inputs_serialization_and_hidden_field_rejection(self):
        raw = [1, 2]
        tick, packet = PublicSignalPublisher(2, 1, 0).publish(0, raw, None)
        raw[0] = 99
        self.assertEqual(tick.raw_counts, (1, 2))
        self.assertFalse(hasattr(packet, "__dict__"))
        with self.assertRaises(FrozenInstanceError):
            packet.signal = (1, 0)
        with self.assertRaises(TypeError):
            packet.source_counts[0][0] = 99
        for record in (tick, packet):
            encoded = json.loads(json.dumps(record.to_dict(), allow_nan=False))
            self.assertEqual(type(record).from_dict(encoded), record)
        data = packet.to_dict()
        data["P_true"] = [.5, .5]
        with self.assertRaises(ValueError):
            ObservationPacket.from_dict(data)
        data = packet.to_dict()
        data["counts"][0] = 900
        with self.assertRaises(ValueError):
            ObservationPacket.from_dict(data)
        self.assertEqual(packet.counts, (1, 2))

    def test_snapshot_json_restores_exact_publication_with_rng_saved_by_world(self):
        rng = np.random.default_rng(78)
        publisher = PublicSignalPublisher(3, 3, 2, noise_sd=.8)
        for step, raw in enumerate(([1, 2, 3], None, [0, 0, 0], [3, 2, 1])):
            publisher.publish(step, raw, rng)
        state = json.loads(json.dumps(publisher.snapshot(), allow_nan=False))
        resumed = PublicSignalPublisher.from_snapshot(state)
        resumed_rng = np.random.default_rng()
        resumed_rng.bit_generator.state = copy.deepcopy(rng.bit_generator.state)
        self.assertEqual(publisher.snapshot(), resumed.snapshot())
        for step, raw in enumerate(([4, 1, 2], None, [0, 1, 0]), start=4):
            self.assertEqual(publisher.publish(step, raw, rng), resumed.publish(step, raw, resumed_rng))
        state["ticks"][0]["raw_counts"] = [100, 100, 100]
        self.assertEqual(publisher.snapshot(), resumed.snapshot())
        # Branch mutation does not alter either the snapshot or sibling state.
        sibling = PublicSignalPublisher.from_snapshot(resumed.snapshot())
        resumed.publish(7, [100, 1, 1], resumed_rng)
        self.assertEqual(sibling.next_step, 7)

    def test_input_and_corrupt_snapshot_validation(self):
        for kwargs in ({"n_topics": 0}, {"window": 0}, {"delay": -1},
                       {"noise_sd": float("nan")}, {"n_topics": True}):
            args = dict(n_topics=2, window=2, delay=0)
            args.update(kwargs)
            with self.assertRaises(ValueError):
                PublicSignalPublisher(**args)
        publisher = PublicSignalPublisher(2, 2, 0)
        for raw in ([1], [1, -1], [1, float("nan")], [True, 1], [1, float("inf")]):
            with self.assertRaises(ValueError):
                publisher.publish(0, raw, None)
            self.assertEqual(publisher.next_step, 0)
        publisher.publish(0, [1, 1], None)
        for step in (0, 2, -1, True):
            with self.assertRaises(ValueError):
                publisher.publish(step, [1, 1], None)
        data = publisher.snapshot()
        data["next_step"] = 3
        with self.assertRaises(ValueError):
            PublicSignalPublisher.from_snapshot(data)
        with self.assertRaises(ValueError):
            PublicTick(0, [0, 0], [1, 1], 2, [.5, .5], "no_interactions")


if __name__ == "__main__":
    unittest.main()
