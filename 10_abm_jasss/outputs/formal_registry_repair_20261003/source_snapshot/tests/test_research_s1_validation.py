"""Read-only S1 reconstruction and semantic tamper rejection on one tiny fixture."""
from contextlib import contextmanager
import copy
import json
from pathlib import Path
import tempfile
import unittest

from abm_jasss.research_s1_cli import run_study
from abm_jasss.research_world import canonical_hash
from scripts.validate_s1_outputs import compare, normalized_artifact, read, sha256, validate


def tiny_spec():
    return {"stage": "S1", "formal_ready": False,
            "model": {"n_agents": 6, "n_topics": 2, "steps": 8, "final_window": 2,
                      "population_weights": [1., 1.], "agenda_topics": [0], "advantaged_topic": 1,
                      "initial_items": 4, "arrivals_per_step": 1, "attention_budget": 2,
                      "survey_size": 3, "survey_interval": 2, "observation_window": 1,
                      "update_frequency": 1, "inference_grid": 2, "reference_agents": 1,
                      "emotion_mean": .8, "emotion_advantage": 0., "official_emotion_mean": .8,
                      "interaction_mean": 1., "interaction_sd": 0., "response_threshold": 0.,
                      "completion_followup": 2, "government_delay": 2},
            "alphas": [.5], "seeds": [811], "administrative_delays": [0, 2],
            "observation_delays": [0], "scheduling_capacities": [1, 2],
            "dynamics": {"alphas": [.2, .8], "stage_ticks": 2,
                         "recovery_fork": 4, "recovery_end": 8,
                         "reference_start": 0, "reference_end": 2, "reference_alpha": 0.,
                         "recovery_window": 2, "recovery_consecutive": 2, "recovery_tolerance": .05,
                         "sizes": [6], "durations": [8], "initial_conditions": {"balanced": [1., 1.]},
                         "supply_scaling": "proportional", "capacity_scaling": "fixed",
                         "interventions": {"control": {}, "information": {"pref_info": True}}}}


class ResearchS1ValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.serial = Path(cls.temporary.name) / "serial"
        cls.parallel = Path(cls.temporary.name) / "parallel"
        for output, workers in ((cls.serial, 1), (cls.parallel, 2)):
            result = run_study(tiny_spec(), output, workers=workers)
            if result["status"] != "complete":
                raise AssertionError(read(output / "failures.json"))
        cls.baseline = "closed_a00_seed811_baseline"
        cls.replay = "replay_a00_seed811_delay0"

    @contextmanager
    def altered(self, replacements, refresh_hashes=True):
        """Restore fixture bytes even when an intentionally forged bundle fails."""
        paths = [self.serial / relative for relative in replacements]
        hash_path = self.serial / "artifact_hashes.json"
        originals = {path: path.read_bytes() for path in paths + [hash_path]}
        try:
            for relative, value in replacements.items():
                (self.serial / relative).write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding="utf-8")
            if refresh_hashes:
                hashes = read(hash_path)
                for relative in replacements:
                    hashes[relative] = sha256(self.serial / relative)
                hash_path.write_text(json.dumps(hashes), encoding="utf-8")
            yield
        finally:
            for path, value in originals.items():
                path.write_bytes(value)

    def changed_state(self, run_id, change, mirrored_log=None):
        snapshot_name = f"raw/{run_id}/evaluator/snapshot.json"
        metadata_name = f"raw/{run_id}/metadata.json"
        snapshot, meta = read(self.serial / snapshot_name), read(self.serial / metadata_name)
        change(snapshot["state"])
        snapshot["state_hash"] = canonical_hash(snapshot["state"])
        meta["final_snapshot_hash"] = snapshot["state_hash"]
        replacements = {snapshot_name: snapshot, metadata_name: meta}
        if mirrored_log:
            field, relative = mirrored_log
            replacements[f"raw/{run_id}/{relative}"] = snapshot["state"]["logs"][field]
        return replacements

    def test_completed_bundle_and_partial_checkpoints_rebuild_without_writes(self):
        before = {path.relative_to(self.serial).as_posix(): sha256(path)
                  for path in self.serial.rglob("*") if path.is_file()}
        result = validate(self.serial)
        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["read_only"])
        self.assertFalse(result["formal_ready"])
        self.assertGreater(result["checkpoint_records"], 0)
        self.assertTrue(result["dynamic_diagnostics_rebuilt"])
        self.assertTrue(result["replay_diagnostics_rebuilt"])
        after = {path.relative_to(self.serial).as_posix(): sha256(path)
                 for path in self.serial.rglob("*") if path.is_file()}
        self.assertEqual(before, after)

    def test_serial_parallel_comparison_preserves_all_model_fields(self):
        result = compare(self.serial, self.parallel)
        self.assertEqual(result["status"], "passed")
        self.assertNotEqual(result["first"]["batch_id"], result["second"]["batch_id"])
        metadata = read(self.serial / "raw" / self.baseline / "metadata.json")
        changed = copy.deepcopy(metadata)
        changed["config"]["government_delay"] += 1
        relative = f"raw/{self.baseline}/metadata.json"
        self.assertNotEqual(normalized_artifact(relative, metadata, metadata["batch_id"]),
                            normalized_artifact(relative, changed, changed["batch_id"]))
        # A nested model field named like execution bookkeeping is retained too.
        manifest = read(self.serial / "manifest.json")
        changed_manifest = copy.deepcopy(manifest)
        changed_manifest["specification"]["model"]["workers"] = 99
        self.assertNotEqual(normalized_artifact("manifest.json", manifest, manifest["batch_id"]),
                            normalized_artifact("manifest.json", changed_manifest, manifest["batch_id"]))

    def test_unhashed_corruption_is_rejected(self):
        relative = f"derived/{self.baseline}.json"
        value = read(self.serial / relative)
        value["mechanisms"]["executed_total"] += 1
        with self.altered({relative: value}, refresh_hashes=False), self.assertRaisesRegex(ValueError, "Artifact hash mismatch"):
            validate(self.serial)

    def test_rehashed_derived_or_paired_statistics_cannot_bypass_reconstruction(self):
        relative = f"derived/{self.baseline}.json"
        value = read(self.serial / relative)
        value["mechanisms"]["executed_total"] += 1
        with self.altered({relative: value}), self.assertRaisesRegex(ValueError, "Derived reconstruction mismatch"):
            validate(self.serial)
        pairs = read(self.serial / "paired_diagnostics.json")
        pairs["0.5"]["closed"]["perception_error"]["trust_interaction"]["scope"] = "forged formal claim"
        with self.altered({"paired_diagnostics.json": pairs}), self.assertRaisesRegex(ValueError, "Paired diagnostic reconstruction mismatch"):
            validate(self.serial)

    def test_rehashed_future_government_packet_and_latent_input_are_rejected(self):
        def future(state):
            info = next(row for row in state["logs"]["information_log"] if row["public_packet"] is not None)
            info["public_packet"]["available_at"] = info["now"] + 1
        updates = self.changed_state(self.baseline, future, ("information_log", "government/information.json"))
        with self.altered(updates), self.assertRaisesRegex(ValueError, "not yet delivered"):
            validate(self.serial)
        def latent(state):
            state["logs"]["information_log"][1]["P_true"] = [.5, .5]
        updates = self.changed_state(self.baseline, latent, ("information_log", "government/information.json"))
        with self.altered(updates), self.assertRaisesRegex(ValueError, "Latent fields"):
            validate(self.serial)

    def test_rehashed_replay_donor_reference_is_rejected(self):
        def change(state):
            state["queue"]["plan"]["donor_information_hash"] = "0" * 64
        updates = self.changed_state(self.replay, change)
        with self.altered(updates), self.assertRaisesRegex(ValueError, "Replay donor reference mismatch"):
            validate(self.serial)

    def test_rehashed_replay_queue_cursor_is_rejected(self):
        def change(state):
            state["queue"]["last_step"] = -1
        updates = self.changed_state(self.replay, change)
        with self.altered(updates), self.assertRaisesRegex(ValueError, "Replay queue disagrees|cursor/boundary mismatch"):
            validate(self.serial)

    def test_rehashed_dynamic_diagnostics_are_rejected(self):
        relative = "diagnostics/dynamics_seed811.json"
        value = read(self.serial / relative)
        value["continuation"]["stages"][0]["window"]["metrics"]["exposure_gap"]["mean"] += .1
        with self.altered({relative: value}), self.assertRaisesRegex(ValueError, "Dynamic diagnostic reconstruction mismatch"):
            validate(self.serial)

    def test_rehashed_world_metadata_and_group_inventory_are_rejected(self):
        relative = f"raw/{self.baseline}/metadata.json"
        value = read(self.serial / relative)
        value["status"] = "checkpoint"
        with self.altered({relative: value}), self.assertRaisesRegex(ValueError, "completion status mismatch"):
            validate(self.serial)
        value = read(self.serial / "validation.json")
        value["groups"][0]["run_ids"].pop()
        with self.altered({"validation.json": value}), self.assertRaisesRegex(ValueError, "Group run inventory mismatch"):
            validate(self.serial)


if __name__ == "__main__":
    unittest.main()
