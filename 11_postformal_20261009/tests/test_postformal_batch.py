"""Real development-only batch I/O with a fixture registry and synchronous workers."""
from concurrent.futures import Future
from contextlib import contextmanager
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from abm_jasss.research_world import ResearchWorld, canonical_hash, source_hash
from postformal.simulation import run as entry, runtime
from postformal.simulation.common import arms, read, sha256, write_json
from test_postformal_runtime import development_job, fingerprint


class ImmediatePool:
    def __init__(self, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def submit(self, function, *args):
        future = Future()
        try:
            future.set_result(function(*args))
        except Exception as error:
            future.set_exception(error)
        return future


class PostformalBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        cls.registry = cls.root / "fixture_registry_not_frozen"
        cls.batch = cls.root / "development_fixture"
        cls.jobs = []
        for alpha in (.25, .75):
            job = copy.deepcopy(development_job())
            job.update(seed=920103, alpha=alpha, group_id=f"no_drift_a{int(alpha * 100)}_seed920103")
            job["model"]["alpha"] = alpha
            cls.jobs.append(job)
        write_json(cls.registry / "resolved_design.json", cls.jobs)
        write_json(cls.registry / "manifest.json", {"test_fixture_only": True, "phase": "supplement",
            "world_records": sum(len(arms(job)) for job in cls.jobs)})
        cls.gate = {"status": "passed", "registry_hash": sha256(cls.registry / "manifest.json"),
                    "inventory_hash": "fixture-inventory", "source_hash": source_hash(),
                    "extension_source_hash": "fixture-extension", "specification_hash": canonical_hash(cls.jobs)}
        with cls.fixture_gates():
            cls.manifest = entry.run_batch(cls.registry, cls.batch, workers=1)

    @classmethod
    @contextmanager
    def fixture_gates(cls):
        with patch.object(entry, "validate_registry", return_value=cls.gate), \
             patch.object(runtime, "authorize_job", return_value=cls.gate), \
             patch.object(entry, "ProcessPoolExecutor", ImmediatePool):
            yield

    def setUp(self):
        self.output = self.root / self._testMethodName

    def validate(self):
        with self.fixture_gates():
            return entry.validate_batch(self.registry, self.batch, self.output, workers=1)

    @contextmanager
    def altered(self, replacements, *, rehash=True):
        inventory_path = self.batch / "artifact_hashes.json"
        targets = [self.batch / relative for relative in replacements] + [inventory_path]
        previous = {path: path.read_bytes() if path.exists() else None for path in targets}
        try:
            for relative, value in replacements.items():
                path = self.batch / relative
                path.write_text(value if isinstance(value, str) else json.dumps(value, allow_nan=False), encoding="utf-8")
            if rehash:
                hashes = {p.relative_to(self.batch).as_posix(): sha256(p)
                          for p in self.batch.rglob("*") if p.is_file() and p != inventory_path}
                inventory_path.write_text(json.dumps(hashes), encoding="utf-8")
            yield
        finally:
            for path, payload in previous.items():
                if payload is None:
                    path.unlink()
                else:
                    path.write_bytes(payload)

    def test_complete_batch_binds_report_records_and_preserves_inputs(self):
        before = fingerprint(self.batch)
        with patch.object(ResearchWorld, "run", side_effect=AssertionError("simulation")), \
             patch.object(ResearchWorld, "step", side_effect=AssertionError("simulation")):
            report = self.validate()
        self.assertEqual(fingerprint(self.batch), before)
        self.assertEqual(report["status"], "passed")
        self.assertTrue(report["read_only"])
        self.assertEqual((report["groups"], report["world_records"], report["trajectory_records"]), (2, 24, 288))
        self.assertEqual(report["batch_manifest_hash"], sha256(self.batch / "manifest.json"))
        self.assertEqual(report["batch_inventory_hash"], sha256(self.batch / "artifact_hashes.json"))
        self.assertEqual(report["records_hash"], sha256(self.output / "records.json.gz"))
        records = read(self.output / "records.json.gz")
        self.assertEqual(len(records["records"]), 26)
        self.assertEqual(len(records["auxiliary_records"]), 26)
        self.assertEqual({r["alpha"] for r in records["records"]}, {.25, .75})

    def test_wrong_manifest_lifecycle_is_rejected_before_validating_groups(self):
        for field, value in (("schema", "wrong"), ("stage", "formal"), ("code_version", "wrong"),
                             ("failures", [{"group_id": self.jobs[0]["group_id"], "error": "retained failure"}])):
            altered = {**self.manifest, field: value}
            with self.subTest(field=field), self.altered({"manifest.json": altered}), \
                 patch.object(entry, "_pool_validate", side_effect=AssertionError("must fail before groups")), \
                 self.assertRaisesRegex(ValueError, "Invalid batch lifecycle"):
                self.validate()
            self.assertFalse(self.output.exists())

    def test_wrong_registry_binding_is_rejected_even_with_refreshed_inventory(self):
        for field in ("registry_hash", "inventory_hash", "source_hash", "extension_source_hash", "specification_hash"):
            altered = {**self.manifest, field: "wrong-binding"}
            with self.subTest(field=field), self.altered({"manifest.json": altered}), \
                 self.assertRaisesRegex(ValueError, "Incomplete/wrong batch|Batch registry binding mismatch"):
                self.validate()
            self.assertFalse(self.output.exists())

    def test_launch_identity_and_lifecycle_must_match_final_manifest(self):
        launch = read(self.batch / "launch.json")
        for field, value in (("batch_id", "another-batch"), ("registry_path", "another-registry"),
                             ("started_at", "another-time"), ("workers", 8), ("status", "complete"),
                             ("completed_groups", 1), ("failures", ["failed"])):
            with self.subTest(field=field), self.altered({"launch.json": {**launch, field: value}}), \
                 self.assertRaisesRegex(ValueError, "Invalid launch lifecycle|Launch/final manifest mismatch"):
                self.validate()
            self.assertFalse(self.output.exists())

    def test_matching_but_wrong_launch_and_final_counts_do_not_change_registry_roster(self):
        launch = read(self.batch / "launch.json")
        for field in ("expected_groups", "expected_world_records"):
            replacements = {"manifest.json": {**self.manifest, field: self.manifest[field] + 1},
                            "launch.json": {**launch, field: launch[field] + 1}}
            with self.subTest(field=field), self.altered(replacements), self.assertRaisesRegex(ValueError, "Incomplete roster"):
                self.validate()
            self.assertFalse(self.output.exists())

    def test_progress_requires_each_registered_group_once_with_exact_success_counts(self):
        original = [json.loads(line) for line in (self.batch / "progress.jsonl").read_text(encoding="utf-8").splitlines()]
        cases = [original[:-1], original + [original[0]],
                 [{**original[0], "group_id": "foreign_group"}, original[1]],
                 [{**original[0], "status": "failed"}, original[1]],
                 [{**original[0], "world_records": original[0]["world_records"] - 1}, original[1]]]
        for index, rows in enumerate(cases):
            content = "".join(json.dumps(row) + "\n" for row in rows)
            with self.subTest(case=index), self.altered({"progress.jsonl": content}), \
                 self.assertRaisesRegex(ValueError, "Invalid progress roster|Progress counts differ"):
                self.validate()
            self.assertFalse(self.output.exists())

    def test_hash_corruption_and_extra_rehashed_artifacts_are_rejected(self):
        with self.altered({"progress.jsonl": ""}, rehash=False), self.assertRaisesRegex(ValueError, "Artifact hash changed"):
            self.validate()
        with self.altered({"unexpected.txt": "unregistered artifact"}), self.assertRaisesRegex(ValueError, "Unexpected batch file set"):
            self.validate()
        self.assertFalse(self.output.exists())

    def test_inventory_is_rechecked_after_workers_finish(self):
        target = self.batch / "diagnostics" / (self.jobs[0]["group_id"] + ".json")
        original = target.read_bytes()
        real_validate = entry._pool_validate
        calls = []
        def mutate_after_reconstruction(args):
            result = real_validate(args)
            calls.append(result)
            if len(calls) == len(self.jobs):
                target.write_bytes(original + b"\n")
            return result
        try:
            with patch.object(entry, "_pool_validate", side_effect=mutate_after_reconstruction), \
                 self.assertRaisesRegex(ValueError, "Artifact hash changed"):
                self.validate()
            self.assertEqual(len(calls), len(self.jobs))
            self.assertFalse((self.output / "validation.json").exists())
            self.assertFalse((self.output / "records.json.gz").exists())
        finally:
            target.write_bytes(original)


if __name__ == "__main__":
    unittest.main()
