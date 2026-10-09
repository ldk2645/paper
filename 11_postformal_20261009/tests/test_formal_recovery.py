"""Tiny explicit fixture recovery; never uses formal registered mother seeds."""
from contextlib import contextmanager, ExitStack
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from abm_jasss.research_replay import ControlledReplayWorld
from abm_jasss.research_world import ResearchWorld
from scripts import formal_runtime as runtime
from scripts import recover_formal_study as recovery
from scripts import run_formal_study as entry
from scripts.formal_artifacts import read, sha256, write_json
from test_formal_cli import fixture, fixture_guard, fixture_gates, ImmediatePool
from test_formal_runtime import fingerprint


@contextmanager
def recovery_gates(jobs):
    with ExitStack() as stack:
        stack.enter_context(fixture_gates(jobs))
        stack.enter_context(patch.object(recovery, "validate_registry", side_effect=lambda path, **kwargs: fixture_guard(path)))
        stack.enter_context(patch.object(recovery, "resolve_formal_design", return_value=jobs))
        stack.enter_context(patch.object(recovery, "ProcessPoolExecutor", ImmediatePool))
        yield


class FormalRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.registry = cls.root / "original_registry"
        cls.jobs, cls.spec = fixture(cls.registry)
        cls.original = cls.root / "original_batch"
        with fixture_gates(cls.jobs):
            cls.original_manifest = entry.run_study(cls.registry, cls.original, workers=1)
        cls.repair_registry = cls.root / "repair_registry"
        shutil.copytree(cls.registry, cls.repair_registry)
        # Explicit mocked registry: not a production release and no real seed audit.
        manifest = read(cls.repair_registry / "manifest.json")
        manifest["fixture_repair_only"] = True
        (cls.repair_registry / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        write_json(cls.repair_registry / "repair_context.json", {
            "parent_registry_hash": sha256(cls.registry / "manifest.json"), "additional_independent_samples": 0})
        (cls.repair_registry / "artifact_hashes.json").unlink()
        entry._write_inventory(cls.repair_registry)

    def test_reexport_all_successful_groups_without_world_construction_restore_or_steps(self):
        output = self.root / "reexported"
        before = fingerprint(self.original)
        with recovery_gates(self.jobs), \
             patch.object(ResearchWorld, "__init__", side_effect=AssertionError("world construction")), \
             patch.object(ResearchWorld, "from_snapshot", side_effect=AssertionError("world restore")), \
             patch.object(ResearchWorld, "run", side_effect=AssertionError("world run")), \
             patch.object(ResearchWorld, "step", side_effect=AssertionError("world step")), \
             patch.object(ControlledReplayWorld, "__init__", side_effect=AssertionError("replay construction")), \
             patch.object(ControlledReplayWorld, "from_snapshot", side_effect=AssertionError("replay restore")), \
             patch.object(ControlledReplayWorld, "run", side_effect=AssertionError("replay run")), \
             patch.object(ControlledReplayWorld, "step", side_effect=AssertionError("replay step")), \
             patch.object(runtime, "run_group", side_effect=AssertionError("complete group was rerun")):
            manifest = recovery.recover_study(self.original, self.repair_registry, output, workers=1)
            report = entry.validate_batch(output, workers=1)
            validation = self.root / "reexported_validation.json"
            write_json(validation, report)
            analysis = entry.analyze_batch(output, self.root / "reexported_analysis", validation)
        self.assertEqual(manifest["status"], "complete")
        self.assertEqual(manifest["complete_records"], 36)
        self.assertEqual(analysis["comparison_count"], 102)
        self.assertEqual(manifest["recovery"]["planned_reused_groups"], 2)
        self.assertEqual(manifest["recovery"]["additional_independent_samples"], 0)
        self.assertEqual(before, fingerprint(self.original))
        for job in self.jobs:
            proof = read(output / "recovery_groups" / f"{job['group_id']}.json")
            self.assertEqual(proof["mode"], "raw_copied_without_world_construction")
            self.assertFalse(proof["world_construction_or_restore_used"])
            self.assertEqual(proof["physical_world_steps_executed"], 0)
            self.assertTrue(proof["raw_bytes_verified"])
            for name, expected in proof["unchanged_raw_gzip_sha256"].items():
                self.assertEqual(expected, sha256(output / name))
                self.assertEqual((self.original / name).read_bytes(), (output / name).read_bytes())
        self.assertEqual((self.original / "manifest.json").read_bytes(),
                         (output / "recovery_source/manifest.json").read_bytes())

    def test_failed_partial_group_is_rerun_whole_and_failure_evidence_retained(self):
        original = self.root / "failed_original"
        actual_run = runtime.run_group
        failed_id = self.jobs[1]["group_id"]

        def fail_after_partial(job, *args):
            if job["group_id"] == failed_id:
                raise RuntimeError("explicit fixture failure before group completion")
            return actual_run(job, *args)

        with fixture_gates(self.jobs), patch.object(runtime, "run_group", side_effect=fail_after_partial):
            with self.assertRaisesRegex(ValueError, "Formal batch failed"):
                entry.run_study(self.registry, original, workers=1)
        # Preserve a subset of an independently generated endpoint as old failed
        # output: recovery must not concatenate it with a partial group.
        first_run = f"E2_{failed_id}_I00"
        shutil.copytree(self.original / "raw" / first_run, original / "raw" / first_run)
        metadata_path = original / "raw" / first_run / "metadata.json"
        metadata = read(metadata_path)
        failed_manifest = read(original / "manifest.json")
        metadata.update(batch_id=failed_manifest["batch_id"])
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        (original / "artifact_hashes.json").unlink()
        entry._write_inventory(original)
        before = fingerprint(original)
        output = self.root / "recovered_failure"
        with recovery_gates(self.jobs), patch.object(runtime, "run_group", wraps=actual_run) as runs:
            manifest = recovery.recover_study(original, self.repair_registry, output, workers=1)
            report = entry.validate_batch(output, workers=1)
        self.assertEqual(runs.call_count, 1)
        self.assertEqual(runs.call_args.args[0], self.jobs[1])
        self.assertEqual(manifest["recovery"]["planned_reused_groups"], 1)
        self.assertEqual(manifest["recovery"]["planned_rerun_groups"], 1)
        self.assertEqual(report["world_records"], 36)
        proof = read(output / "recovery_groups" / f"{failed_id}.json")
        self.assertEqual(proof["mode"], "entire_original_group_rerun")
        self.assertEqual(proof["new_endpoint_count"], 18)
        self.assertFalse(proof["raw_bytes_verified"])
        self.assertTrue(proof["source_files_sha256"])
        self.assertEqual(before, fingerprint(original))
        self.assertEqual(read(original / "manifest.json")["status"], "failed")
        self.assertEqual(read(output / "recovery_source/failures.json"), read(original / "failures.json"))

    def test_input_tampering_is_rejected_before_models_or_output(self):
        original = self.root / "tampered"
        shutil.copytree(self.original, original)
        path = original / "groups" / f"{self.jobs[0]['group_id']}.json"
        path.write_text("{}", encoding="utf-8")
        output = self.root / "tampered_output"
        with recovery_gates(self.jobs), patch.object(ResearchWorld, "run", side_effect=AssertionError("world run")):
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                recovery.recover_study(original, self.repair_registry, output)
        self.assertFalse(output.exists())

    def test_wrong_parent_or_changed_design_never_runs(self):
        for label, change in (("parent", "parent"), ("design", "design")):
            registry = self.root / (label + "_registry")
            shutil.copytree(self.repair_registry, registry)
            if change == "parent":
                path = registry / "repair_context.json"
                value = read(path)
                value["parent_registry_hash"] = "0" * 64
            else:
                path = registry / "configuration.json"
                value = read(path)
                value["seeds"] = [97232]
            path.write_text(json.dumps(value), encoding="utf-8")
            output = self.root / (label + "_output")
            with recovery_gates(self.jobs), patch.object(runtime, "run_group", side_effect=AssertionError("group run")):
                with self.assertRaises(ValueError):
                    recovery.recover_study(self.original, registry, output)
            self.assertFalse(output.exists())

    def test_direct_copy_rejects_rehashed_metadata_seed_or_snapshot_binding(self):
        job = self.jobs[0]
        run_id = f"E2_{job['group_id']}_I00"
        source = self.root / "forged_endpoint_metadata"
        shutil.copytree(self.original / "raw" / run_id, source / "raw" / run_id)
        path = source / "raw" / run_id / "metadata.json"
        metadata = read(path)
        source_files = recovery._job_source_files(job, read(self.original / "artifact_hashes.json"))
        with recovery_gates(self.jobs):
            binding = runtime._authorize(self.repair_registry, job, self.original_manifest["source_hash"])
        manifest = dict(self.original_manifest, batch_id="fixture_direct_copy_new_batch")
        for field, value in (("seed", 97232), ("final_snapshot_hash", "0" * 64), ("config_hash", "0" * 64)):
            with self.subTest(field=field):
                path.write_text(json.dumps(dict(metadata, **{field: value})), encoding="utf-8")
                source_files[f"raw/{run_id}/metadata.json"] = sha256(path)
                output = self.root / ("forged_" + field + "_output")
                with self.assertRaisesRegex(ValueError, "metadata does not reconstruct"):
                    recovery._copy_endpoint(job, source, output, manifest, self.original_manifest,
                                            binding, "E2", "I00", source_files)
                self.assertFalse(output.exists())

    def test_direct_copy_rejects_changed_snapshot_even_with_rehashed_raw(self):
        job = self.jobs[0]
        run_id = f"E2_{job['group_id']}_I00"
        source = self.root / "forged_endpoint_snapshot"
        shutil.copytree(self.original / "raw" / run_id, source / "raw" / run_id)
        path = source / "raw" / run_id / recovery.artifacts.SNAPSHOT_FILE
        snapshot = read(path)
        snapshot["state"]["seed"] += 1
        path.unlink()
        recovery.artifacts.write_gzip_json(path, snapshot)
        metadata_path = source / "raw" / run_id / "metadata.json"
        metadata = read(metadata_path)
        metadata["raw_sha256"][recovery.artifacts.SNAPSHOT_FILE] = sha256(path)
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        source_files = recovery._job_source_files(job, read(self.original / "artifact_hashes.json"))
        source_files[f"raw/{run_id}/metadata.json"] = sha256(metadata_path)
        source_files[f"raw/{run_id}/{recovery.artifacts.SNAPSHOT_FILE}"] = sha256(path)
        with recovery_gates(self.jobs):
            binding = runtime._authorize(self.repair_registry, job, self.original_manifest["source_hash"])
        output = self.root / "forged_snapshot_output"
        with self.assertRaisesRegex(ValueError, "Snapshot hash mismatch"):
            recovery._copy_endpoint(job, source, output, self.original_manifest, self.original_manifest,
                                    binding, "E2", "I00", source_files)
        self.assertFalse(output.exists())

    def test_reexport_failure_preserves_failed_new_batch(self):
        output = self.root / "bad_restore_output"
        before = fingerprint(self.original)
        with recovery_gates(self.jobs), patch.object(recovery.artifacts, "build_formal_derived", side_effect=ValueError("fixture export failure")):
            with self.assertRaisesRegex(ValueError, "Formal recovery failed"):
                recovery.recover_study(self.original, self.repair_registry, output, workers=1)
        self.assertEqual(read(output / "manifest.json")["status"], "failed")
        self.assertEqual(len(read(output / "failures.json")), 2)
        self.assertFalse((output / "statistical_records.json").exists())
        self.assertEqual(before, fingerprint(self.original))

    def test_running_source_and_existing_output_are_rejected(self):
        output = self.root / "existing"
        output.mkdir()
        with self.assertRaisesRegex(ValueError, "already exists"):
            recovery.recover_study(self.original, self.repair_registry, output)
        source = self.root / "running_source"
        shutil.copytree(self.original, source)
        path = source / "manifest.json"
        manifest = read(path)
        manifest["status"] = "running"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        (source / "artifact_hashes.json").unlink()
        entry._write_inventory(source)
        output = self.root / "running_rejected"
        with recovery_gates(self.jobs), patch.object(runtime, "run_group", side_effect=AssertionError("group run")):
            with self.assertRaisesRegex(ValueError, "not finalized"):
                recovery.recover_study(source, self.repair_registry, output)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
