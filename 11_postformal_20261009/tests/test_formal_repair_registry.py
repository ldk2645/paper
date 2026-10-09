"""Software repair registration preserves original units and frozen inference."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from abm_jasss.research_world import ResearchWorld, canonical_hash
from scripts import formal_registry as registry
import test_formal_registry as fixtures


class FormalRepairRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Reuse the explicit synthetic source/test-evidence fixture. No model
        # construction or registered seed execution occurs in these tests.
        fixtures.FormalRegistryTests.setUpClass.__func__(cls)
        cls.parent = cls.output
        cls.parent_result = cls.result
        diagnostic = registry.REPAIR_DIAGNOSTIC_DIRECTORY
        for name in ("job.json", "failure.json", "diagnostic_manifest.json", "execute.py", "inspect_distance.py"):
            target = cls.root / diagnostic / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(registry.ROOT / diagnostic / name, target)
        inspection = "i11_distance_inspection"
        shutil.copytree(registry.ROOT / diagnostic / inspection, cls.root / diagnostic / inspection)
        for relative in ("diagnostic_manifest.json", f"{inspection}/diagnostic_manifest.json"):
            path = cls.root / diagnostic / relative
            data = registry.read(path)
            data["registry_hash"] = cls.parent_result["registry_hash"]
            fixtures.write(path, data)
        cls.refresh_inventory(cls.root / diagnostic / inspection)
        changed = cls.root / "scripts/formal_artifacts.py"
        changed.write_bytes(changed.read_bytes() + b"\n# Synthetic software-only repair fixture.\n")
        evidence = registry.read(cls.evidence)
        evidence["source_sha256"] = registry.source_inventory(cls.root)
        fixtures.write(cls.evidence, evidence)
        cls.repair = cls.root / "outputs/repaired"
        with patch.object(ResearchWorld, "__init__", side_effect=AssertionError("physical construction")), \
             patch.object(registry, "audit_seeds", side_effect=AssertionError("must inherit original audit")):
            cls.repair_result = registry.build_registry(cls.config, cls.repair, protocol_path=cls.protocol,
                test_evidence_path=cls.evidence, root=cls.root, parent_registry=cls.parent)

    @staticmethod
    def refresh_inventory(directory):
        inventory = directory / "artifact_hashes.json"
        fixtures.write(inventory, {path.relative_to(directory).as_posix(): registry.sha256(path)
                                  for path in sorted(directory.rglob("*")) if path.is_file() and path != inventory})

    @contextmanager
    def changed_file(self, path, value, *, rehash=False, update_context=False):
        inventory = self.repair / "artifact_hashes.json"
        parent_inventory = self.repair / "parent_registry/artifact_hashes.json"
        manifest_path = self.repair / "manifest.json"
        saved = {p: p.read_bytes() for p in (path, inventory, parent_inventory, manifest_path)}
        try:
            if isinstance(value, bytes):
                path.write_bytes(value)
            else:
                fixtures.write(path, value)
            if update_context:
                manifest = registry.read(manifest_path)
                manifest["repair_context_hash"] = canonical_hash(registry.read(self.repair / "repair_context.json"))
                fixtures.write(manifest_path, manifest)
            if rehash:
                if path.is_relative_to(self.repair / "parent_registry"):
                    self.refresh_inventory(self.repair / "parent_registry")
                self.refresh_inventory(self.repair)
            yield
        finally:
            for saved_path, content in saved.items():
                saved_path.write_bytes(content)

    def test_repair_reuses_exact_units_audit_and_parent_archive_without_physics(self):
        with patch.object(ResearchWorld, "step", side_effect=AssertionError("physical step")):
            checked = registry.validate_registry(self.repair, root=self.root)
        self.assertEqual(checked, self.repair_result)
        context = registry.read(self.repair / "repair_context.json")
        self.assertEqual(context["additional_independent_samples"], 0)
        self.assertEqual(context["parent_registry_hash"], self.parent_result["registry_hash"])
        self.assertEqual(context["changed_source_paths"], ["scripts/formal_artifacts.py"])
        self.assertIn("original_seed_registration_preserved", checked["manifest"]["gates"])
        self.assertNotIn("unused_seed_registry", checked["manifest"]["gates"])
        self.assertEqual(checked["manifest"]["expected_world_records"], 21312)
        for name in registry.REPAIR_INHERITED_FILES:
            self.assertEqual((self.parent / name).read_bytes(), (self.repair / name).read_bytes())
        original_files = {p.relative_to(self.parent).as_posix(): registry.sha256(p)
                          for p in self.parent.rglob("*") if p.is_file()}
        archived = self.repair / "parent_registry"
        self.assertEqual(original_files, {p.relative_to(archived).as_posix(): registry.sha256(p)
                                          for p in archived.rglob("*") if p.is_file()})
        self.assertEqual(registry.validate_registry(self.parent, root=self.root, check_live=False), self.parent_result)
        for relative, digest in context["diagnostic_evidence_hashes"].items():
            self.assertEqual(registry.sha256(self.repair / "evidence/project" / relative), digest)

    def test_repair_rejects_changed_seeds_inference_and_specification(self):
        mutations = (
            lambda value: value.update(seeds=[seed + len(value["seeds"]) for seed in value["seeds"]]),
            lambda value: value["inference"].update(min_joint_valid=2),
            lambda value: value["model"].update(steps=value["model"]["steps"] + 1),
        )
        original = self.config.read_bytes()
        try:
            for index, mutate in enumerate(mutations):
                value = deepcopy(self.spec)
                mutate(value)
                fixtures.write(self.config, value)
                output = self.root / f"outputs/rejected_spec_{index}"
                with self.subTest(index=index), self.assertRaises(ValueError):
                    registry.build_registry(self.config, output, protocol_path=self.protocol,
                        test_evidence_path=self.evidence, root=self.root, parent_registry=self.parent)
                self.assertFalse(output.exists())
        finally:
            self.config.write_bytes(original)

    def test_repair_rejects_physics_dependencies_and_unapproved_inference_code(self):
        for index, relative in enumerate(("abm_jasss/research_world.py", "requirements.txt",
                                           "scripts/formal_inference.py", "scripts/run_formal_study.py")):
            path = self.root / relative
            original, old_evidence = path.read_bytes(), self.evidence.read_bytes()
            output = self.root / f"outputs/rejected_code_{index}"
            try:
                path.write_bytes(original + b"\n# Unapproved changed source.\n")
                evidence = registry.read(self.evidence)
                evidence["source_sha256"] = registry.source_inventory(self.root)
                fixtures.write(self.evidence, evidence)
                with self.subTest(relative=relative), self.assertRaises(ValueError):
                    registry.build_registry(self.config, output, protocol_path=self.protocol,
                        test_evidence_path=self.evidence, root=self.root, parent_registry=self.parent)
                self.assertFalse(output.exists())
            finally:
                path.write_bytes(original)
                self.evidence.write_bytes(old_evidence)

    def test_rehashed_context_policy_and_parent_tampering_fail_semantics(self):
        context = registry.read(self.repair / "repair_context.json")
        context["additional_independent_samples"] = 1
        policy = registry.read(self.repair / "numeric_repair_policy.json")
        policy["absolute_tolerance"] *= 2
        parent = registry.read(self.repair / "parent_registry/manifest.json")
        parent["gates"]["final_tests_passed"] = False
        for relative, value in (("repair_context.json", context), ("numeric_repair_policy.json", policy),
                                 ("parent_registry/manifest.json", parent)):
            with self.subTest(relative=relative), self.changed_file(self.repair / relative, value, rehash=True,
                    update_context=relative == "repair_context.json"), self.assertRaises(ValueError):
                registry.validate_registry(self.repair, root=self.root, check_live=False)

    def test_repair_rejects_stale_full_test_evidence_before_creating_output(self):
        path = self.root / "scripts/formal_registry.py"
        original = path.read_bytes()
        output = self.root / "outputs/rejected_stale_tests"
        try:
            path.write_bytes(original + b"\n# Changed after full test evidence.\n")
            with self.assertRaisesRegex(ValueError, "does not cover current source"):
                registry.build_registry(self.config, output, protocol_path=self.protocol,
                    test_evidence_path=self.evidence, root=self.root, parent_registry=self.parent)
            self.assertFalse(output.exists())
        finally:
            path.write_bytes(original)

    def test_repair_rejects_second_layer_and_never_overwrites(self):
        for output, parent, expected in ((self.repair, self.parent, "already exists"),
                (self.root / "outputs/rejected_second_layer", self.repair, "one software repair layer")):
            with self.subTest(expected=expected), self.assertRaisesRegex(ValueError, expected):
                registry.build_registry(self.config, output, protocol_path=self.protocol,
                    test_evidence_path=self.evidence, root=self.root, parent_registry=parent)

    def test_rehashed_inherited_seed_audit_and_missing_diagnostic_are_rejected(self):
        value = registry.read(self.repair / "seed_audit.json")
        value["scope"] += " changed"
        with self.changed_file(self.repair / "seed_audit.json", value, rehash=True), self.assertRaises(ValueError):
            registry.validate_registry(self.repair, root=self.root)
        path = self.repair / "evidence/project" / registry.REPAIR_DIAGNOSTIC_DIRECTORY / "failure.json"
        value = registry.read(path)
        value["status"] = "not_reproduced"
        with self.changed_file(path, value, rehash=True), self.assertRaises(ValueError):
            registry.validate_registry(self.repair, root=self.root)


if __name__ == "__main__":
    unittest.main()
