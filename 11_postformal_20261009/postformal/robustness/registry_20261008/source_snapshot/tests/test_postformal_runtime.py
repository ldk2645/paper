"""Small development fixtures; no supplement registry or production seeds are used."""
from contextlib import contextmanager
import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from abm_jasss.research_config import ResearchConfig, RESEARCH_VERSION
from abm_jasss.research_replay import PLAN_FIELDS
from abm_jasss.research_world import ResearchWorld, canonical_hash, source_hash
from postformal.simulation import runtime
from postformal.simulation.common import AUXILIARY, BRANCHES, PRIMARY, arms, read, sha256


def development_job():
    config = ResearchConfig(n_agents=6, n_topics=2, steps=12, final_window=4,
        population_weights=(1., 1.), agenda_topics=(0,), advantaged_topic=1,
        initial_items=4, arrivals_per_step=1, attention_budget=2,
        survey_size=3, survey_interval=2, observation_window=1,
        update_frequency=1, inference_grid=2, reference_agents=1,
        emotion_mean=.8, emotion_advantage=0., official_emotion_mean=.8,
        interaction_mean=1., interaction_sd=0., response_threshold=0.,
        completion_start=6, completion_end=9, completion_followup=2,
        government_delay=3, response_capacity=1, observation_delay=0,
        alpha=.25, drift_rate=0.)
    return {"group_id": "no_drift_a25_seed920101", "variant": "no_drift",
            "seed": 920101, "alpha": .25, "model": config.to_dict(), "fork_tick": 6,
            "branches": copy.deepcopy(BRANCHES),
            "closed": {"delay0": {"government_delay": 0}}, "replay_delays": [0, 3]}


def fingerprint(path):
    return {p.relative_to(path).as_posix(): (sha256(p), p.stat().st_mtime_ns)
            for p in path.rglob("*") if p.is_file()}


class PostformalRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.output = Path(cls.temporary.name) / "development_only"
        cls.job = development_job()
        cls.gate = {"registry_hash": "development-fixture-only",
                    "source_hash": source_hash(), "extension_source_hash": "fixture"}
        cls.manifest = {**cls.gate, "code_version": RESEARCH_VERSION,
                        "batch_id": "development-test-only", "registry_path": "unused"}
        with patch.object(runtime, "authorize_job", return_value=cls.gate):
            cls.result = runtime.run_group(cls.job, cls.output, cls.manifest["batch_id"],
                                           cls.gate["source_hash"], "unused")

    def validate(self):
        with patch.object(runtime, "authorize_job", return_value=self.gate):
            return runtime.validate_group(self.job, self.output, self.manifest)

    def snapshot(self, family, arm):
        return read(self.output / "raw" / f"{family}_{self.job['group_id']}_{arm}" / "snapshot.json.gz")

    @contextmanager
    def altered(self, relative, value, *, rehash=True):
        path = self.output / relative
        group_path = self.output / "groups" / (self.job["group_id"] + ".json")
        originals = {p: p.read_bytes() for p in (path, group_path)}
        def replace_json(target, data):
            payload = json.dumps(data, sort_keys=True, allow_nan=False).encode("utf-8")
            target.write_bytes(gzip.compress(payload, mtime=0) if target.suffix == ".gz" else payload)
        try:
            replace_json(path, value)
            if rehash and path != group_path:
                group = read(group_path)
                group["files"][relative] = sha256(path)
                replace_json(group_path, group)
            yield
        finally:
            for target, payload in originals.items():
                target.write_bytes(payload)

    def test_all_arms_reconstruct_read_only_with_individual_no_drift(self):
        before = fingerprint(self.output)
        with patch.object(ResearchWorld, "run", side_effect=AssertionError("simulation during validation")), \
             patch.object(ResearchWorld, "step", side_effect=AssertionError("step during validation")), \
             patch.object(runtime, "write_json", side_effect=AssertionError("write during validation")), \
             patch.object(runtime, "write_gzip_json", side_effect=AssertionError("write during validation")):
            result = self.validate()
        self.assertEqual(before, fingerprint(self.output))
        self.assertEqual(self.result["world_records"], 12)
        self.assertEqual(result["world_records"], 12)
        self.assertEqual(result["trajectory_records"], 12 * 12)
        self.assertGreater(result["response_events"], 0)
        self.assertEqual(len(result["records"]), 13)  # closed-loop baseline reuses E2 I00
        self.assertEqual(len(result["auxiliary_records"]), 13)
        self.assertTrue(all(set(r["metrics"]) == set(PRIMARY) for r in result["records"]))
        self.assertTrue(all(set(r["values"]) == set(AUXILIARY) for r in result["auxiliary_records"]))
        diagnostics = read(self.output / "diagnostics" / (self.job["group_id"] + ".json"))
        self.assertEqual(set(diagnostics["no_drift"]), {f + "/" + a for f, a, _ in arms(self.job)})
        for check in diagnostics["no_drift"].values():
            self.assertEqual(check["individual_max_abs_difference"], 0.)
            self.assertLessEqual(check["aggregate_max_abs_difference"], 1e-12)
            self.assertEqual(check["initial_preferences_hash"], check["final_preferences_hash"])
            self.assertEqual(check["ticks_checked"], 12)
        records = {(r["family"], r["arm"]): r for r in result["records"]}
        self.assertEqual(records["E2", "I00"]["metrics"], records["E3_closed", "baseline"]["metrics"])

    def test_replay_uses_complete_unbranched_donor_and_unchanged_plan(self):
        donor = self.snapshot("E2", "I00")
        self.assertIsNone(donor["state"]["parent_world_id"])
        self.assertEqual(donor["state"]["tick"], self.job["model"]["steps"])
        plan_events = [{k: event[k] for k in PLAN_FIELDS} for event in donor["state"]["logs"]["events"]]
        self.assertTrue(plan_events)
        for delay in (0, 3):
            state = self.snapshot("E3_replay", "delay" + str(delay))["state"]
            plan = state["queue"]["plan"]
            self.assertEqual(plan["donor_snapshot_hash"], donor["state_hash"])
            self.assertEqual(plan["donor_information_hash"], canonical_hash(donor["state"]["logs"]["information_log"]))
            self.assertEqual(plan["events"], plan_events)
            self.assertEqual(state["logs"]["supply_log"], donor["state"]["logs"]["supply_log"])
            for event in state["logs"]["events"]:
                self.assertEqual(event["due_step"], event["trigger_step"] + delay)
                self.assertEqual(event["decision_mode"], "controlled_fixed_plan")

    def test_no_drift_rejects_truncated_or_nonfinite_vectors(self):
        state = self.snapshot('E2', 'I00')['state']
        initial = read(self.output/'initial_arrays'/(self.job['group_id']+'.json'))
        mutations = [lambda x:x['arrays']['preferences'][0].pop(),
                     lambda x:x['logs']['trajectory'][0]['P_true'].pop(),
                     lambda x:x['arrays']['preferences'][0].__setitem__(0,float('nan'))]
        for mutate in mutations:
            changed = copy.deepcopy(state)
            mutate(changed)
            with self.assertRaisesRegex(ValueError,'dimensions or values invalid'):
                runtime._nodrift(changed, initial)

    def test_no_drift_rejects_individual_changes_even_when_population_mean_is_preserved(self):
        state = self.snapshot("E2", "I00")["state"]
        initial = read(self.output / "initial_arrays" / (self.job["group_id"] + ".json"))
        state["arrays"]["preferences"].reverse()
        self.assertNotEqual(state["arrays"]["preferences"], initial["preferences"])
        with self.assertRaisesRegex(ValueError, "No Drift changed preferences"):
            runtime._nodrift(state, initial)

    def test_unhashed_mutation_is_rejected_before_semantic_reconstruction(self):
        relative = f"derived/E2_{self.job['group_id']}_I00.json"
        altered = read(self.output / relative)
        altered["summary"]["execution_count"] += 1
        with self.altered(relative, altered, rehash=False), \
             self.assertRaisesRegex(ValueError, "Group artifact corruption"):
            self.validate()

    def test_rehashed_derived_metadata_and_diagnostics_mutations_are_rejected(self):
        group = self.job["group_id"]
        cases = [(f"derived/E2_{group}_I00.json", "Derived values mismatch"),
                 (f"raw/E3_replay_{group}_delay0/metadata.json", "Metadata mismatch"),
                 (f"diagnostics/{group}.json", "Diagnostics mismatch")]
        for relative, message in cases:
            altered = read(self.output / relative)
            if relative.startswith("derived"):
                altered["summary"]["execution_count"] += 1
            elif relative.startswith("raw"):
                altered["provenance"]["donor_run_id"] = "wrong-donor"
            else:
                altered["no_drift"]["E2/I00"]["individual_max_abs_difference"] = .1
            with self.subTest(relative=relative), self.altered(relative, altered), \
                 self.assertRaisesRegex(ValueError, message):
                self.validate()

    def test_rehashed_replay_with_another_donor_is_rejected(self):
        relative = f"raw/E3_replay_{self.job['group_id']}_delay0/snapshot.json.gz"
        snapshot = read(self.output / relative)
        snapshot["state"]["queue"]["plan"]["donor_seed"] = 920102
        snapshot["state_hash"] = canonical_hash(snapshot["state"])
        with self.altered(relative, snapshot), self.assertRaisesRegex(ValueError, "Replay donor mismatch"):
            self.validate()

    def test_completed_group_refuses_overwrite(self):
        before = fingerprint(self.output)
        with patch.object(runtime, "authorize_job", return_value=self.gate), self.assertRaises(FileExistsError):
            runtime.run_group(self.job, self.output, self.manifest["batch_id"], self.gate["source_hash"], "unused")
        self.assertEqual(before, fingerprint(self.output))


if __name__ == "__main__":
    unittest.main()
