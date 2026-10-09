"""Temporary readiness fixtures: no production seeds or physical study runs."""
import copy
from contextlib import contextmanager
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from postformal.simulation import registry as reg
from postformal.simulation.common import read, write_json, inventory, canonical_hash, sha256, source_hash


class PostformalRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        cls.spec = read(reg.ROOT/'postformal/robustness/configs/supplement_20261007.json')
        cls.spec = copy.deepcopy(cls.spec)
        cls.spec['seeds'] = [920104]
        cls.spec['variants'] = cls.spec['variants'][:1]
        cls.ext, cls.dep, cls.tests = reg.extension_inventory(), reg.dependency_inventory(), reg.test_inventory()
        evidence = {'status':'passed','tests_run':1,'failures':0,'errors':0,
                    'extension_source_hash':canonical_hash(cls.ext), 'dependency_source_hash':canonical_hash(cls.dep),
                    'physical_source_hash':source_hash(), 'test_source_sha256':cls.tests}
        log = cls.root/'tests.log'
        log.write_text('test_fixture ... ok\n\nRan 1 test in 0.01s\n\nOK\n', encoding='utf-8')
        evidence['tests_log_hash'] = sha256(log)
        write_json(cls.root/'tests.json', evidence)
        cls.evidence = evidence
        audit = {'schema_version':'postformal-seed-audit-1', 'status':'passed','collisions':[],
                 'candidate_count':1,'candidate_hash':canonical_hash(cls.spec['seeds']),
                 'historical_seeds':[920101], 'historical_seed_count':1,
                 'checked_files':{'test-fixture':'fixture'}, 'development_files':{}}
        write_json(cls.root/'audit.json', audit)
        write_json(cls.root/'config.json', cls.spec)
        (cls.root/'protocol.md').write_text('Temporary readiness fixture only. No models executed.', encoding='utf-8')
        cases = [{'variant':'baseline','alpha':a,'seed':920105,'world_records':12,
                  'run_seconds':1.,'validation_seconds':1.,'bytes':1,
                  'read_only_reconstruction':'passed'} for a in cls.spec['alphas']]
        cls.benchmark = {'status':'passed','stage':'postformal_development_preflight','outcomes_inspected':False,
                         'primary_inference_generated':False,'seed':920105,'source_hash':source_hash(),
                         'extension_source_hash':canonical_hash(cls.ext),'dependency_source_hash':canonical_hash(cls.dep),
                         'specification_hash':canonical_hash(cls.spec),'cases':cases,
                         'projected_serial_run_seconds':2.,'projected_serial_validation_seconds':2.,'projected_batch_bytes':2}
        write_json(cls.root/'benchmark/report.json', cls.benchmark)
        inventory(cls.root/'benchmark')
        original_hash = sha256(reg.ORIGINAL/'manifest.json')
        cls.frozen = cls.root/'frozen_fixture'
        with patch.object(reg,'validate_original',return_value={'registry_hash':original_hash}), \
             patch.object(reg,'build_seed_audit',return_value=audit):
            cls.gate = reg.freeze(cls.root/'config.json',cls.frozen,cls.root/'protocol.md',
                                  cls.root/'tests.json',cls.root/'audit.json',cls.root/'benchmark/report.json')

    def test_complete_frozen_fixture_and_registered_job_authorize(self):
        job = reg.resolve(self.spec)[0]
        gate = reg.authorize_job(self.frozen, job, source_hash())
        self.assertEqual(gate['registry_hash'], self.gate['registry_hash'])
        altered = copy.deepcopy(job)
        altered['model']['survey_size'] = 24
        with self.assertRaisesRegex(ValueError,'Unregistered job'):
            reg.authorize_job(self.frozen, altered, source_hash())

    def test_cached_authorization_still_checks_artifact_bytes(self):
        job = reg.resolve(self.spec)[0]
        reg.authorize_job(self.frozen, job, source_hash())
        path = self.frozen/'protocol.md'
        original = path.read_bytes()
        try:
            path.write_bytes(original+b' changed')
            with self.assertRaisesRegex(ValueError,'Artifact hash changed'):
                reg.authorize_job(self.frozen, job, source_hash())
        finally:
            path.write_bytes(original)

    def test_cached_authorization_checks_live_shared_dependency(self):
        job = reg.resolve(self.spec)[0]
        reg.authorize_job(self.frozen, job, source_hash())
        altered = dict(self.dep, **{'scripts/formal_inference.py':'changed'})
        with patch.object(reg,'dependency_inventory',return_value=altered), \
             self.assertRaisesRegex(ValueError,'Live source changed'):
            reg.authorize_job(self.frozen, job, source_hash())

    def test_preflight_requires_every_case_and_disjoint_seed(self):
        for mutate in (lambda x:x['cases'].pop(), lambda x:x['cases'].append(x['cases'][0]),
                       lambda x:x.update(seed=920104), lambda x:x['cases'][0].update(world_records=1),
                       lambda x:x.update(projected_batch_bytes=3), lambda x:x.update(primary_inference_generated=True)):
            report = copy.deepcopy(self.benchmark)
            mutate(report)
            with self.subTest(report=str(report)[-90:]), self.assertRaises(ValueError):
                reg._benchmark_evidence(report,self.spec,self.ext,self.dep)

    def test_test_evidence_rejects_empty_or_unbound_suite(self):
        for change in ({'tests_run':0}, {'dependency_source_hash':'wrong'}, {'failures':1},
                       {'tests_log_hash':'wrong'}, {'test_source_sha256':{}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                reg._test_evidence(dict(self.evidence,**change),self.root/'tests.log',self.ext,self.dep,self.tests)

    def test_invalid_design_and_seed_collision_rejected(self):
        for mutate in (lambda x:x['seeds'].append(x['seeds'][0]),
                       lambda x:x['variants'][0]['changes'].update(drift_rate=0.),
                       lambda x:x['variants'][0]['branches'].append('B0'),
                       lambda x:x['inference'].update(additional_sampling=True),
                       lambda x:x['variants'][0].update(fork_tick=True)):
            spec = copy.deepcopy(self.spec)
            mutate(spec)
            with self.assertRaises(ValueError):
                reg.resolve(spec)
        audit=read(self.root/'audit.json')
        audit.update(historical_seeds=[920104])
        with self.assertRaisesRegex(ValueError,'Seed audit mismatch'):
            reg._validate_seed_audit(audit,self.spec['seeds'])


if __name__ == '__main__':
    unittest.main()
