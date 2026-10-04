"""Explicit synthetic-only reporting fixture; never creates or advances a model.

The numerical entries are invented to test presentation and missingness states.
They are not estimates, accepted analysis results, or candidate formal seeds.
"""
import argparse
import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import report_formal_results as report


def synthetic_rows():
    limited = {("E3_closed", .75, "delay0", "platform_representation_gap"): 1293,
               ("E3_closed", .75, "delay0", "targeting_error_trigger"): 1071,
               ("E3_replay", .75, "delay3", "platform_representation_gap"): 1002}
    rows = []
    for index, (family, alpha, contrast, metric) in enumerate(report.expected_keys()):
        total = 184 if alpha == .25 else 1000
        joint = total - (index % 5)
        none = min(1, total - joint)
        mean = math.sin(index * 1.7) * (.09 if metric == "platform_representation_gap" else .018)
        half = .006 + .003 * (index % 8)
        status = "estimated"
        if index == 0:
            status, joint, none = "insufficient_joint_support", 18, 160
        elif index == 1:
            status, mean = "degenerate_sample_variance", 0.
        elif index == 2:
            status, joint, none, mean = "insufficient_joint_support", 0, total, None
        available = status == "estimated"
        rejected = available and index % 4 == 0
        sd = half * math.sqrt(joint) / 2 if joint > 1 else None
        key = family, alpha, contrast, metric
        rows.append({"family": family, "alpha": alpha, "contrast": contrast, "metric": metric, "status": status,
            "n_total": total, "n_joint_valid": joint, "n_single_sided_valid": total - joint - none,
            "n_partially_valid": total - joint - none, "n_none_valid": none,
            "mean": mean, "sample_sd": 0. if status == "degenerate_sample_variance" else sd,
            "standard_error": 0. if status == "degenerate_sample_variance" else sd / math.sqrt(joint) if sd is not None else None,
            "degrees_of_freedom": joint - 1 if joint > 1 else None,
            "confidence_half_width": half if available else None,
            "p_value_two_sided": .0001 if rejected else .5 if available else None,
            "p_value_holm": .01 if rejected else 1., "p_value_numerical_floor": False,
            "reject_holm_0_05": rejected, "observed_target_half_width_met": half <= .02 if available else None,
            "ci_lower": mean - half if available else None, "ci_upper": mean + half if available else None,
            "pilot_budget_limited": key in limited, "pilot_required_total_uncapped": limited.get(key),
            "pilot_variance_unstable": index < 61})
    return rows


def synthetic_auxiliary():
    return [{"family": "E2", "alpha": "0.25", "arm": "I00", "metric": metric,
             "n_total": "184", "n_valid": str(valid), "mean": mean,
             "scope": "descriptive_equal_weight_mother_world_means"}
            for metric, valid, mean in (("has_response", 184, "0.8"), ("waiting_time", 147, "3.0"),
                ("platform_signal_coverage", 184, "0.95"), ("perception_data_coverage", 184, "0.99"))]


def synthetic_inference(rows):
    groups = []
    for family in report.ORDER:
        for alpha in (.25, .75):
            contrasts = {}
            for row in rows:
                if (row["family"], row["alpha"]) != (family, alpha):
                    continue
                item = {k: row[k] for k in report.COPY_FIELDS}
                item.update(status=row["status"], additional_sampling=False,
                    estimand="mean_paired_contrast_conditional_on_joint_support",
                    confidence_interval=[row["ci_lower"], row["ci_upper"]] if row["ci_lower"] is not None else None)
                contrasts.setdefault(row["contrast"], {})[row["metric"]] = item
            groups.append({"family": family, "alpha": alpha, "contrasts": contrasts,
                           "operationally_complete": True, "missing_records": [], "failed_records": []})
    return {"groups": groups}


def make_mock_inputs(base):
    """Fixture-only minimal archive; real registry validation is mocked in tests."""
    from scripts.formal_inference import INFERENCE_POLICY
    rows = synthetic_rows()
    analysis, registry = base / "synthetic_analysis", base / "synthetic_registry"
    analysis.mkdir()
    planning = registry / "evidence/project/outputs/synthetic_planning"
    planning.mkdir(parents=True)
    spec = {"sample_sizes": {"0.25": 184, "0.75": 1000}, "seeds": list(range(1, 1001)),
            "inference": INFERENCE_POLICY, "evidence": {"pilot_planning": "outputs/synthetic_planning"}}
    report.write_json(registry / "configuration.json", spec)
    report.write_json(planning / "stability.json", {"items": [{"family": r["family"], "alpha": r["alpha"],
        "contrast": r["contrast"], "metric": r["metric"], "variance_stable": not r["pilot_variance_unstable"]} for r in rows]})
    gate = {"registry_hash": "a" * 64, "source_hash": "b" * 64, "specification_hash": "c" * 64,
            "artifact_inventory_hash": "d" * 64,
            "manifest": {"pilot_check": {"budget_limited_items": [{"family": r["family"], "alpha": r["alpha"],
                "contrast": r["contrast"], "metric": r["metric"], "required_total_uncapped": r["pilot_required_total_uncapped"]}
                for r in rows if r["pilot_budget_limited"]]}}}
    manifest = {"schema_version": "formal-analysis-1", "stage": "formal_analysis", "formal_ready": True,
        "semantic_validation_complete": True, "additional_sampling": False, "comparison_count": 102,
        "batch_id": "SYNTHETIC_FIXTURE_NOT_A_FORMAL_BATCH", "manifest_hash": "1" * 64,
        "artifact_inventory_hash": "2" * 64, "validation_report_hash": "3" * 64,
        **{k: gate[k] for k in ("registry_hash", "source_hash", "specification_hash")}}
    inference = synthetic_inference(rows)
    inference.update(schema="formal-inference-1", operationally_complete=True, comparison_count=102,
        additional_sampling=False, inference=INFERENCE_POLICY,
        parent_ids_by_alpha={a: [str(s) for s in spec["seeds"][:n]] for a, n in spec["sample_sizes"].items()})
    report.write_json(analysis / "analysis_manifest.json", manifest)
    report.write_json(analysis / "inference.json", inference)
    report.csv_write(analysis / "primary.csv", report.primary_rows(inference))
    report.csv_write(analysis / "auxiliary.csv", synthetic_auxiliary())
    report.write_inventory(analysis)
    return analysis, registry, gate


class ReportingChecks(unittest.TestCase):
    def test_all_102_comparisons_and_limitations(self):
        rows = synthetic_rows()
        summary = report.summary(rows, synthetic_auxiliary(), {}, synthetic=True)
        self.assertEqual(102, summary["comparison_count"])
        self.assertEqual(3, summary["pilot_budget_limited_count"])
        self.assertEqual(61, summary["pilot_variance_unstable_count"])
        self.assertEqual(3, summary["target_unavailable"])
        self.assertEqual(102, len(summary["support_and_precision_by_comparison"]))

    def test_duplicate_comparison_rejected(self):
        inference = synthetic_inference(synthetic_rows())
        inference["groups"].append(copy.deepcopy(inference["groups"][0]))
        with self.assertRaisesRegex(ValueError, "102 comparisons"):
            report.primary_rows(inference)

    def test_support_accounting_rejected(self):
        inference = synthetic_inference(synthetic_rows())
        inference["groups"][0]["contrasts"]["interaction"]["perception_error"]["n_total"] += 1
        with self.assertRaisesRegex(ValueError, "support accounting"):
            report.primary_rows(inference)

    def test_mock_bound_input_and_mutated_bytes(self):
        with tempfile.TemporaryDirectory(prefix="fixture_gate_", dir=report.TOOLS) as directory:
            analysis, registry, gate = make_mock_inputs(Path(directory))
            with patch("scripts.formal_registry.validate_registry", return_value=gate):
                rows, _, provenance = report.load_accepted(analysis, registry)
                self.assertEqual(102, len(rows))
                self.assertTrue(provenance["semantic_validation_complete"])
                with (analysis / "primary.csv").open("a", encoding="utf-8") as stream:
                    stream.write("\n")
                with self.assertRaisesRegex(ValueError, "Artifact hash mismatch"):
                    report.load_accepted(analysis, registry)

    def test_rehashed_unaccepted_manifest_rejected(self):
        with tempfile.TemporaryDirectory(prefix="fixture_gate_", dir=report.TOOLS) as directory:
            analysis, registry, gate = make_mock_inputs(Path(directory))
            for field, value in (("semantic_validation_complete", False), ("additional_sampling", True),
                                 ("registry_hash", "0" * 64)):
                original = report.read(analysis / "analysis_manifest.json")
                changed = dict(original, **{field: value})
                (analysis / "analysis_manifest.json").write_text(json.dumps(changed), encoding="utf-8")
                # A malicious rehash cannot bypass semantic and registry checks.
                hashes = report.read(analysis / "artifact_hashes.json")
                hashes["analysis_manifest.json"] = report.digest(analysis / "analysis_manifest.json")
                (analysis / "artifact_hashes.json").write_text(json.dumps(hashes), encoding="utf-8")
                with patch("scripts.formal_registry.validate_registry", return_value=gate):
                    with self.assertRaises(ValueError):
                        report.load_accepted(analysis, registry)
                (analysis / "analysis_manifest.json").write_text(json.dumps(original), encoding="utf-8")

    def test_rehashed_csv_different_from_json_rejected(self):
        with tempfile.TemporaryDirectory(prefix="fixture_gate_", dir=report.TOOLS) as directory:
            analysis, registry, gate = make_mock_inputs(Path(directory))
            rows = report.csv_read(analysis / "primary.csv")
            rows[0]["mean"] = "999"
            (analysis / "primary.csv").unlink()
            report.csv_write(analysis / "primary.csv", rows)
            hashes = report.read(analysis / "artifact_hashes.json")
            hashes["primary.csv"] = report.digest(analysis / "primary.csv")
            (analysis / "artifact_hashes.json").write_text(json.dumps(hashes), encoding="utf-8")
            with patch("scripts.formal_registry.validate_registry", return_value=gate):
                with self.assertRaisesRegex(ValueError, "CSV/inference mismatch"):
                    report.load_accepted(analysis, registry)

    def test_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory(prefix="fixture_existing_", dir=report.TOOLS) as directory:
            with self.assertRaisesRegex(ValueError, "Output exists"):
                report.render(synthetic_rows(), synthetic_auxiliary(), {}, directory, synthetic=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render-output", type=Path)
    args = parser.parse_args()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ReportingChecks))
    if not result.wasSuccessful():
        raise SystemExit(1)
    if args.render_output:
        provenance = {"scope": "INDEPENDENT_SYNTHETIC_FIXTURE_ONLY", "no_models_created_or_stepped": True,
                      "fixture_generator_sha256": report.digest(__file__)}
        manifest = report.render(synthetic_rows(), synthetic_auxiliary(), provenance, args.render_output, synthetic=True)
        print(json.dumps({"synthetic_fixture_only": True, "checks_passed": result.testsRun,
                          "output": str(args.render_output), "renderer": manifest["renderer"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
