"""Precision raw compression, lineage and read-only reconstruction contracts."""
import gzip
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from abm_jasss.research_config import ResearchConfig
from abm_jasss.research_replay import make_replay_worlds
from abm_jasss.research_world import ResearchWorld, canonical_hash, source_hash
from scripts.precision_artifacts import (ACTIONS_FILE, LOG_FILES, SNAPSHOT_FILE,
    read, save_world, sha256, validate_world_folder, write_gzip_json, write_json)


def small_config(**changes):
    values = dict(n_agents=6, n_topics=2, steps=8, final_window=2,
        population_weights=(1., 1.), agenda_topics=(0,), advantaged_topic=1,
        initial_items=4, arrivals_per_step=2, attention_budget=2,
        survey_size=4, survey_interval=1, pref_info=True, inference_grid=2,
        reference_agents=2, update_frequency=1, response_threshold=0.,
        government_delay=0, completion_followup=2)
    values.update(changes)
    return ResearchConfig(**values)


def fingerprint(root):
    return {path.relative_to(root).as_posix(): (sha256(path), path.stat().st_mtime_ns)
            for path in root.rglob("*") if path.is_file()}


class PrecisionArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "batch"
        self.expected_hash = source_hash()

    def save(self, world, name="closed_group_baseline", output=None, **kwargs):
        return save_world(world, output or self.output, "pilot-test", name, "group",
                          "replay" if "replay" in name else "closed", "baseline",
                          self.expected_hash, **kwargs)

    def folder(self, name="closed_group_baseline"):
        return self.output / "raw" / name

    def rewrite(self, path, value):
        """Only adversarial fixtures replace bytes; production writers never do."""
        import json
        payload = json.dumps(value, sort_keys=True, allow_nan=False).encode()
        path.write_bytes(gzip.compress(payload, compresslevel=1, mtime=0)
                         if path.suffix == ".gz" else payload)

    def rehash(self, folder):
        metadata = read(folder / "metadata.json")
        metadata["raw_sha256"] = {relative: sha256(folder / relative)
                                  for relative in metadata["raw_sha256"]}
        self.rewrite(folder / "metadata.json", metadata)

    def test_zero_positive_delays_and_read_only_reconstruction(self):
        for delay in (0, 3):
            with self.subTest(delay=delay):
                world = ResearchWorld(small_config(government_delay=delay), 7201).run()
                name = f"closed_group_delay{delay}"
                expected = self.save(world, name)
                self.assertTrue(world.events)
                before = fingerprint(self.output)
                with patch.object(ResearchWorld, "step", side_effect=AssertionError("physical step")), \
                     patch.object(ResearchWorld, "run", side_effect=AssertionError("physical run")), \
                     patch("scripts.precision_artifacts.write_json", side_effect=AssertionError("write")), \
                     patch("scripts.precision_artifacts.write_gzip_json", side_effect=AssertionError("write")):
                    self.assertEqual(validate_world_folder(self.folder(name), self.expected_hash), expected)
                self.assertEqual(fingerprint(self.output), before)
                meta = read(self.folder(name) / "metadata.json")
                self.assertEqual(meta["stage"], "precision_pilot")
                self.assertEqual(meta["schema_version"], "precision-artifacts-1")
                self.assertFalse(meta["formal_ready"])
                actions = read(self.folder(name) / ACTIONS_FILE)
                self.assertTrue(all("P_trigger" not in row and "P_execution" not in row for row in actions))

    def test_gzip_bytes_and_raw_inventory_are_deterministic(self):
        world = ResearchWorld(small_config(), 7202).run()
        first = self.save(world)
        other = Path(self.temp.name) / "second"
        self.assertEqual(first, self.save(world, output=other))
        folder = self.folder()
        expected = {"metadata.json", SNAPSHOT_FILE, ACTIONS_FILE, *LOG_FILES.values()}
        self.assertEqual({path.relative_to(folder).as_posix() for path in folder.rglob("*")
                          if path.is_file()}, expected)
        for path in folder.rglob("*.gz"):
            payload = path.read_bytes()
            self.assertEqual(payload[4:8], b"\x00\x00\x00\x00")
            self.assertEqual(payload, (other / "raw" / folder.name / path.relative_to(folder)).read_bytes())
        self.assertEqual(read(folder / SNAPSHOT_FILE), world.snapshot())

    def test_existing_world_or_derived_is_never_overwritten(self):
        world = ResearchWorld(small_config(), 7203).run()
        self.save(world)
        before = fingerprint(self.output)
        with self.assertRaisesRegex(ValueError, "must not exist"):
            self.save(world)
        self.assertEqual(fingerprint(self.output), before)
        orphan = self.output / "derived" / "new.json"
        write_json(orphan, {"historical": True})
        with self.assertRaisesRegex(ValueError, "must not exist"):
            self.save(world, "new")
        self.assertEqual(read(orphan), {"historical": True})
        self.assertFalse(self.folder("new").exists())

    def test_fork_after_information_change_and_analysis_window_override(self):
        parent = ResearchWorld(small_config(pref_info=False, government_delay=3), 7204).run(until=3)
        parent_snapshot = parent.snapshot()
        self.save(parent, "parent")
        branches = [parent.fork("control"), parent.fork("survey", {"pref_info": True, "government_delay": 1})]
        for world in branches:
            world.run()
            name = world.world_id.rsplit("/", 1)[-1]
            expected = self.save(world, name, analysis_config={"completion_start": 3,
                                                               "completion_end": 5})
            with self.assertRaisesRegex(ValueError, "Missing/cyclic ancestor"):
                validate_world_folder(self.folder(name), self.expected_hash)
            before = fingerprint(self.output)
            self.assertEqual(validate_world_folder(self.folder(name), self.expected_hash,
                {parent_snapshot["state_hash"]: parent_snapshot}), expected)
            self.assertEqual(fingerprint(self.output), before)
            meta = read(self.folder(name) / "metadata.json")
            self.assertEqual(meta["config"]["pref_info"], name == "survey")
            self.assertEqual(meta["analysis_config"]["completion_start"], 3)
            self.assertEqual(meta["parent_snapshot_hash"], parent_snapshot["state_hash"])

    def test_replay_validation_reads_fixed_queue_without_running_world(self):
        donor = ResearchWorld(small_config(), 7205).run()
        self.save(donor, "donor")
        for delay, world in make_replay_worlds(donor, (0, 3)).items():
            world.run()
            name = f"replay_delay{delay}"
            expected = self.save(world, name, provenance={"donor_run_id": "donor",
                "replay_plan_hash": world.replay_plan.plan_hash})
            with patch.object(ResearchWorld, "step", side_effect=AssertionError("physical step")):
                self.assertEqual(validate_world_folder(self.folder(name), self.expected_hash), expected)

    def test_boundary_zero_and_nonterminal_checkpoint(self):
        for tick in (0, 3):
            world = ResearchWorld(small_config(), 7206).run(until=tick)
            name = f"checkpoint{tick}"
            expected = self.save(world, name)
            self.assertEqual(validate_world_folder(self.folder(name), self.expected_hash), expected)
            self.assertEqual(read(self.folder(name) / "metadata.json")["status"], "checkpoint")
            self.assertIsNone(expected["summary"]["platform_representation_gap"])

    def test_raw_tampering_fails_hash_and_semantic_checks(self):
        self.save(ResearchWorld(small_config(), 7207).run())
        folder = self.folder()
        path = folder / LOG_FILES["government_estimates"]
        records = read(path)
        records[0]["estimate"] = [.9, .1]
        self.rewrite(path, records)
        with self.assertRaisesRegex(ValueError, "Artifact hash mismatch"):
            validate_world_folder(folder, self.expected_hash)
        self.rehash(folder)
        with self.assertRaisesRegex(ValueError, "Snapshot/log mismatch"):
            validate_world_folder(folder, self.expected_hash)

    def test_metadata_derived_and_snapshot_tampering_are_rejected(self):
        world = ResearchWorld(small_config(), 7208).run()
        for target in ("metadata", "derived", "snapshot"):
            self.save(world, target)
            folder = self.folder(target)
            if target == "metadata":
                path = folder / "metadata.json"
                value = read(path)
                value["information_condition"]["PrefInfo"] = False
            elif target == "derived":
                path = self.output / "derived" / f"{target}.json"
                value = read(path)
                value["summary"]["execution_count"] += 1
            else:
                path = folder / SNAPSHOT_FILE
                value = read(path)
                value["state"]["seed"] += 1
            self.rewrite(path, value)
            if target == "snapshot":
                self.rehash(folder)
            with self.subTest(target=target), self.assertRaises(ValueError):
                validate_world_folder(folder, self.expected_hash)

    def test_rehashed_illegal_estimate_is_rejected_by_decision_reconstruction(self):
        self.save(ResearchWorld(small_config(), 7211).run())
        folder = self.folder()
        snapshot = read(folder / SNAPSHOT_FILE)
        estimates = snapshot["state"]["logs"]["government_estimates"]
        estimates[0]["estimate"] = [.91, .09]
        snapshot["state_hash"] = canonical_hash(snapshot["state"])
        self.rewrite(folder / SNAPSHOT_FILE, snapshot)
        self.rewrite(folder / LOG_FILES["government_estimates"], estimates)
        metadata = read(folder / "metadata.json")
        metadata["final_snapshot_hash"] = snapshot["state_hash"]
        metadata["log_hashes"]["government_estimates"] = canonical_hash(estimates)
        self.rewrite(folder / "metadata.json", metadata)
        self.rehash(folder)
        with self.assertRaisesRegex(ValueError, "Government estimate reconstruction mismatch"):
            validate_world_folder(folder, self.expected_hash)

    def test_strict_json_rejects_duplicate_nonfinite_and_overflow_numbers(self):
        for compressed in (False, True):
            for payload in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e999}'):
                with self.subTest(compressed=compressed, payload=payload):
                    path = Path(self.temp.name) / ("bad.json.gz" if compressed else "bad.json")
                    path.write_bytes(gzip.compress(payload) if compressed else payload)
                    with self.assertRaises(ValueError):
                        read(path)
        for writer in (write_json, write_gzip_json):
            path = Path(self.temp.name) / writer.__name__
            with self.assertRaises(ValueError):
                writer(path, {"bad": float("inf")})
            self.assertFalse(path.exists())

    def test_publication_reconstruction_supports_noise_missing_signals_and_delay(self):
        configurations = ({"observation_noise": .7, "observation_delay": 2},
                          {"sampling_rate": 0.}, {"interaction_mean": 0., "interaction_sd": 0.})
        for index, changes in enumerate(configurations):
            with self.subTest(changes=changes):
                name = f"publication{index}"
                world = ResearchWorld(small_config(**changes), 7212).run()
                expected = self.save(world, name)
                with patch.object(ResearchWorld, "step", side_effect=AssertionError("physical step")):
                    self.assertEqual(validate_world_folder(self.folder(name), self.expected_hash), expected)

    def test_consistently_hashed_publication_corruption_is_rejected(self):
        # Exporting these fixtures refreshes every snapshot/log/derived hash,
        # so rejection must come from the independent publication reconstruction.
        for target in ("public_tick", "trajectory", "pending_packet", "delivery", "publisher"):
            with self.subTest(target=target):
                world = ResearchWorld(small_config(observation_delay=2), 7213).run()
                if target == "public_tick":
                    world.public_signal_ticks[-1]["signal"] = [.123, .877]
                elif target == "trajectory":
                    row = world.trajectory[-1]
                    row["S_public"] = [.123, .877]
                    row["platform_representation_gap"] = .5 * sum(
                        abs(a - b) for a, b in zip(row["P_true"], row["S_public"]))
                elif target == "pending_packet":
                    world.pending_packets[-1]["available_at"] += 1
                elif target == "delivery":
                    world.observation_packets.pop()
                else:
                    world.publisher.next_step += 1
                self.save(world, target)
                with self.assertRaisesRegex(ValueError, "reconstruction mismatch"):
                    validate_world_folder(self.folder(target), self.expected_hash)

    def test_analysis_override_cannot_disguise_physical_model_or_change_horizon(self):
        world = ResearchWorld(small_config(), 7209).run()
        for override in ({"pref_info": False}, {"steps": 9}, {"extra": 1}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                self.save(world, analysis_config=override)
            self.assertFalse(self.output.exists())

    def test_hash_source_inventory_and_path_guards(self):
        world = ResearchWorld(small_config(), 7210).run()
        with self.assertRaisesRegex(ValueError, "Source changed"):
            save_world(world, self.output, "b", "r", "g", "s", "c", "wrong")
        for name in ("../escape", "..", "x/y", "x\\y", "x."):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.save(world, name)
        self.save(world)
        write_json(self.folder() / "unexpected.json", {})
        with self.assertRaisesRegex(ValueError, "inventory mismatch"):
            validate_world_folder(self.folder(), self.expected_hash)


if __name__ == "__main__":
    unittest.main()
