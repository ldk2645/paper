"""Independent supplement registry with complete executable and evidence bindings."""
from dataclasses import replace
from functools import lru_cache
import math
import platform
import re
import shutil
import numpy as np
from .common import *
from abm_jasss.research_config import ResearchConfig
from scripts.formal_registry import (validate_registry as validate_original,
                                     audit_seeds as audit_original_seeds, _seed_values)

ORIGINAL = ROOT / 'outputs/formal_registry_repair_v2_20261003'
EXTENSION = Path(__file__).resolve().parent
BASE_CONFIG = 'configs/formal_design_20261003.json'
ALLOWED_CHANGES = frozenset(('inference_grid', 'reference_agents', 'reference_seed',
    'survey_size', 'opaque_alpha', 'regularization', 'survey_weight', 'drift_rate',
    'n_agents', 'steps', 'final_window', 'completion_start', 'completion_end'))


def _file(root, relative):
    require(isinstance(relative, str) and relative and '\\' not in relative and
            not Path(relative).is_absolute() and '..' not in Path(relative).parts,
            'Unsafe registry artifact path')
    root = Path(root).resolve()
    path = root / relative
    require(path.is_file() and path.resolve().is_relative_to(root) and
            not any(p.is_symlink() for p in (path, *path.parents) if p != root),
            'Missing or symlink artifact: ' + relative)
    return path


def _inventory(paths, root):
    root = Path(root).resolve()
    result = {}
    for path in sorted(paths):
        relative = Path(path).relative_to(root).as_posix()
        result[relative] = sha256(_file(root, relative))
    require(bool(result), 'Empty source inventory')
    return result


def extension_inventory():
    return _inventory(EXTENSION.rglob('*.py'), ROOT)


def dependency_inventory():
    """Include imported shared scripts, physical code and dependency declarations."""
    paths = [p for folder in ('abm_jasss', 'scripts') for p in (ROOT / folder).rglob('*.py')]
    paths += [ROOT / 'requirements.txt', ROOT / BASE_CONFIG, ROOT / 'postformal/__init__.py']
    return _inventory(paths, ROOT)


def test_inventory():
    return _inventory((ROOT / 'tests').glob('test_*.py'), ROOT)


def resolve(spec):
    require(isinstance(spec, dict) and spec.get('schema') == 'postformal-design-1', 'Wrong study schema')
    require(spec.get('phase') in ('development', 'supplement'), 'Unknown phase')
    seeds = spec['seeds']
    require(isinstance(seeds, list) and bool(seeds) and
            all(type(s) is int and s >= 0 for s in seeds) and len(seeds) == len(set(seeds)),
            'Invalid seed roster')
    require(spec['alphas'] == [.25, .75], 'Both registered alpha settings required')
    variants = spec['variants']
    require(isinstance(variants, list) and variants and all(isinstance(v, dict) for v in variants),
            'Missing variants')
    ids = [v['id'] for v in variants]
    require(all(isinstance(x, str) and re.fullmatch(r'[a-z][a-z0-9_]*', x) for x in ids),
            'Unsafe variant identifier')
    require(ids[0] == 'baseline' and len(ids) == len(set(ids)), 'Invalid variants')
    base = ResearchConfig.from_dict(spec['base_model'])
    require(jsonable(base.to_dict()) == spec['base_model'], 'Base model must contain the complete configuration')
    if spec['phase'] == 'supplement':
        require(spec['base_model'] == read(ROOT / BASE_CONFIG)['model'], 'Baseline differs from original formal design')
    require(base.reference_seed not in seeds, 'Reference seed overlaps study seeds')
    require(variants[0]['changes'] == {}, 'Baseline cannot contain alternative changes')
    jobs = []
    for variant in variants:
        require(set(variant) == {'id', 'changes', 'fork_tick', 'branches', 'closed', 'replay_delays'},
                'Unknown or missing variant fields')
        changes = variant['changes']
        require(isinstance(changes, dict) and set(changes) <= ALLOWED_CHANGES, 'Unregistered parameter change')
        branches = variant['branches']
        require(isinstance(branches, list) and all(isinstance(a, str) for a in branches) and
                len(branches) == len(set(branches)) and set(branches) <= set(BRANCHES) and
                {'B0', 'B1', 'B4'} <= set(branches), 'Invalid branches')
        require(variant['closed'] in ({}, {'delay0': {'government_delay': 0}}), 'Invalid closed subset')
        require(variant['replay_delays'] in ([], [0, 3]) and
                all(type(d) is int for d in variant['replay_delays']), 'Invalid replay subset')
        if variant['id'] == 'no_drift':
            require(changes == {'drift_rate': 0.0} and set(branches) == set(BRANCHES) and
                    bool(variant['closed']) and variant['replay_delays'] == [0, 3], 'Incomplete No Drift design')
        for alpha in spec['alphas']:
            cfg = ResearchConfig.from_dict(dict(base.to_dict(), **dict(changes, alpha=alpha)))
            require(type(variant['fork_tick']) is int and 0 < variant['fork_tick'] < cfg.steps, 'Invalid fork')
            require(cfg.reference_seed not in seeds, 'Variant reference seed overlaps study seeds')
            analysis = cfg.analysis_config()
            require(analysis['completion_end'] + cfg.completion_followup < cfg.steps,
                    'Completion cohort lacks its full follow-up window')
            for seed in seeds:
                jobs.append({'group_id': f"{variant['id']}_a{int(alpha * 100):02d}_seed{seed}",
                    'variant': variant['id'], 'alpha': alpha, 'seed': seed, 'model': cfg.to_dict(),
                    'fork_tick': variant['fork_tick'], 'branches': {a: BRANCHES[a] for a in branches},
                    'closed': variant['closed'], 'replay_delays': variant['replay_delays']})
    baseline = variants[0]
    for variant in variants[1:]:
        require(set(variant['branches']) <= set(baseline['branches']) and
                (not variant['closed'] or bool(baseline['closed'])) and
                (not variant['replay_delays'] or baseline['replay_delays'] == [0, 3]),
                'Alternative contrasts lack matching baseline arms')
    inference = spec['inference']
    require(type(inference['min_joint_valid']) is int and inference['min_joint_valid'] == 30 and
            inference['sd_floor'] == 1e-12 and inference['confidence'] == .95 and
            inference['holm_families'] == ['within_variant', 'effect_change'] and
            inference['additional_sampling'] is False and
            type(inference['target_half_width']) in (float, int) and
            math.isfinite(inference['target_half_width']) and 0 < inference['target_half_width'] <= 1 and
            isinstance(inference['budget_policy'], str) and bool(inference['budget_policy'].strip()),
            'Unsupported inference or stopping policy')
    return jsonable(jobs)


def build_seed_audit(seeds):
    """Audit historical studies and the separately retained development runs."""
    report = audit_original_seeds(seeds, root=ROOT)
    used = set(report['historical_seeds'])
    candidates = set(seeds)
    development_files = {}
    for path in sorted((EXTENSION / 'development').rglob('*.json')):
        if path.name.startswith('seed_audit') or path.name == 'artifact_hashes.json':
            continue
        relative = path.relative_to(ROOT).as_posix()
        development_files[relative] = sha256(_file(ROOT, relative))
        values = set(_seed_values(read(path)))
        used.update(values)
        overlap = values & candidates
        if overlap:
            report['collisions'].append({'path': relative, 'method': 'postformal_development_json_seed_fields',
                                         'seeds': sorted(overlap)})
    report.update(schema_version='postformal-seed-audit-1',
                  status='failed' if report['collisions'] else 'passed',
                  historical_seeds=sorted(used), historical_seed_count=len(used),
                  development_files=development_files,
                  scope=report['scope'] + '; supplementary development JSON seed fields')
    return report


def _validate_seed_audit(audit, seeds):
    require(audit.get('schema_version') == 'postformal-seed-audit-1' and
            audit.get('status') == 'passed' and audit.get('collisions') == [] and
            audit.get('candidate_count') == len(seeds) and
            audit.get('candidate_hash') == canonical_hash(seeds) and
            bool(audit.get('checked_files')) and isinstance(audit.get('development_files'), dict) and
            not set(audit['historical_seeds']) & set(seeds) and
            audit['historical_seed_count'] == len(set(audit['historical_seeds'])), 'Seed audit mismatch')


def _test_evidence(report, log, ext, dependencies, tests):
    require(report.get('status') == 'passed' and type(report.get('tests_run')) is int and
            report['tests_run'] > 0 and report.get('failures') == 0 and report.get('errors') == 0,
            'Tests did not pass a nonempty suite')
    require(report.get('extension_source_hash') == canonical_hash(ext) and
            report.get('dependency_source_hash') == canonical_hash(dependencies) and
            report.get('physical_source_hash') == source_hash() and
            report.get('test_source_sha256') == tests, 'Tests do not bind complete current source')
    require(sha256(log) == report.get('tests_log_hash'), 'Test log hash mismatch')
    content = Path(log).read_text(encoding='utf-8-sig')
    match = re.search(r'Ran (\d+) tests? in [^\r\n]+[\r\n]+\s*OK(?: \(skipped=\d+\))?\s*\Z', content)
    require(match is not None and int(match[1]) == report['tests_run'] and
            not re.search(r'^(?:FAILED \(|ERROR: |FAIL: |UNEXPECTED SUCCESS: )', content, re.MULTILINE),
            'Test log is incomplete or inconsistent')


def _benchmark_evidence(report, spec, ext, dependencies):
    require(report.get('status') == 'passed' and report.get('stage') == 'postformal_development_preflight' and
            report.get('outcomes_inspected') is False and report.get('source_hash') == source_hash() and
            report.get('extension_source_hash') == canonical_hash(ext) and
            report.get('dependency_source_hash') == canonical_hash(dependencies) and
            report.get('specification_hash') == canonical_hash(spec),
            'Preflight does not bind the complete proposed study and source')
    require(report.get('primary_inference_generated') is False and type(report.get('seed')) is int and
            report['seed'] not in spec['seeds'], 'Preflight must use a disjoint development seed')
    expected = {(v['id'], alpha): 4 + len(v['branches']) + len(v['closed']) + len(v['replay_delays'])
                for v in spec['variants'] for alpha in spec['alphas']}
    cases = report.get('cases', [])
    observed = {}
    for case in cases:
        key = (case['variant'], case['alpha'])
        require(key in expected and key not in observed and case['seed'] == report['seed'] and
                case['read_only_reconstruction'] == 'passed' and case['world_records'] == expected[key],
                'Preflight case roster or reconstruction mismatch')
        require(all(type(case[k]) in (int, float) and math.isfinite(case[k]) and case[k] > 0
                    for k in ('run_seconds', 'validation_seconds', 'bytes')), 'Invalid preflight resource record')
        observed[key] = case['world_records']
    require(observed == expected, 'Incomplete preflight case coverage')
    for field, measurement in (('projected_serial_run_seconds', 'run_seconds'),
                               ('projected_serial_validation_seconds', 'validation_seconds'),
                               ('projected_batch_bytes', 'bytes')):
        require(report.get(field) == sum(c[measurement] for c in cases)*len(spec['seeds']),
                'Preflight budget projection mismatch')


def freeze(config, output, protocol, tests, seed_audit, benchmark):
    # New supplementary tests must not rewrite the historical formal source inventory.
    original = validate_original(ORIGINAL, check_live=False)
    spec = read(config)
    jobs = resolve(spec)
    require(spec['phase'] == 'supplement', 'Only supplement registry can freeze for production')
    ext, dependencies, test_sources = extension_inventory(), dependency_inventory(), test_inventory()
    evidence = read(tests)
    log = Path(tests).parent / 'tests.log'
    _test_evidence(evidence, log, ext, dependencies, test_sources)
    audit = read(seed_audit)
    _validate_seed_audit(audit, spec['seeds'])
    require(audit == build_seed_audit(spec['seeds']), 'Seed audit is stale; regenerate before freezing')
    _benchmark_evidence(read(benchmark), spec, ext, dependencies)
    check_inventory(Path(benchmark).parent)
    require(Path(protocol).is_file() and bool(Path(protocol).read_text(encoding='utf-8').strip()), 'Empty protocol')
    out = new_directory(output)
    write_json(out / 'configuration.json', spec)
    write_json(out / 'resolved_design.json', jobs)
    for source, name in ((protocol, 'protocol.md'), (tests, 'test_evidence.json'), (log, 'tests.log'),
                         (seed_audit, 'seed_audit.json'), (benchmark, 'benchmark.json'),
                         (ORIGINAL / 'manifest.json', 'original_manifest.json'),
                         (ORIGINAL / 'artifact_hashes.json', 'original_inventory.json')):
        shutil.copyfile(source, out / name)
    all_sources = {**ext, **dependencies, **test_sources}
    for relative in all_sources:
        target = out / 'source_snapshot' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_file(ROOT, relative), target)
    manifest = {'schema': 'postformal-registry-1', 'phase': spec['phase'], 'status': 'frozen',
        'created_at': utc(), 'source_hash': source_hash(), 'original_registry_hash': original['registry_hash'],
        'original_inventory_hash': sha256(out / 'original_inventory.json'),
        'extension_sha256': ext, 'extension_source_hash': canonical_hash(ext),
        'dependency_sha256': dependencies, 'dependency_source_hash': canonical_hash(dependencies),
        'test_source_sha256': test_sources, 'source_snapshot_sha256': all_sources,
        'specification_hash': canonical_hash(spec), 'resolved_design_hash': canonical_hash(jobs),
        'groups': len(jobs), 'world_records': sum(len(arms(j)) for j in jobs),
        'independent_seeds': len(spec['seeds']), 'protocol_hash': sha256(out / 'protocol.md'),
        'numpy_version': np.__version__, 'python_version': platform.python_version(),
        'seed_audit_hash': canonical_hash(audit), 'test_evidence_hash': canonical_hash(evidence),
        'benchmark_hash': sha256(out / 'benchmark.json')}
    write_json(out / 'manifest.json', manifest)
    inventory(out)
    return validate_registry(out)


def validate_registry(path):
    path = Path(path)
    require(not path.is_symlink(), 'Symlink registry')
    path = path.resolve()
    digest, _ = check_inventory(path)
    m = read(path / 'manifest.json')
    require(m['schema'] == 'postformal-registry-1' and m['status'] == 'frozen' and
            m['phase'] == 'supplement', 'Registry is not a frozen supplement')
    require(source_hash() == m['source_hash'], 'Physical model changed')
    require(extension_inventory() == m['extension_sha256'] and
            canonical_hash(m['extension_sha256']) == m['extension_source_hash'], 'Supplement code changed after freeze')
    require(dependency_inventory() == m['dependency_sha256'] and
            canonical_hash(m['dependency_sha256']) == m['dependency_source_hash'], 'Executable dependency changed after freeze')
    require(test_inventory() == m['test_source_sha256'], 'Test source changed after freeze')
    require(np.__version__ == m['numpy_version'] and platform.python_version() == m['python_version'],
            'Runtime dependency version changed after freeze')
    sources = {**m['extension_sha256'], **m['dependency_sha256'], **m['test_source_sha256']}
    require(sources == m['source_snapshot_sha256'], 'Incomplete frozen source map')
    actual_sources = {p.relative_to(path / 'source_snapshot').as_posix(): sha256(p)
                      for p in sorted((path / 'source_snapshot').rglob('*')) if p.is_file()}
    require(actual_sources == sources, 'Archived source differs from freeze')
    require(sha256(path / 'original_manifest.json') == m['original_registry_hash'] and
            sha256(path / 'original_inventory.json') == m['original_inventory_hash'], 'Original registry identity mismatch')
    original_manifest, original_inventory = read(path / 'original_manifest.json'), read(path / 'original_inventory.json')
    require(original_inventory.get('manifest.json') == m['original_registry_hash'] and
            original_manifest['source_hash'] == m['source_hash'] and original_manifest['status'] == 'frozen',
            'Original registry provenance mismatch')
    spec = read(path / 'configuration.json')
    jobs = resolve(spec)
    require(spec['phase'] == m['phase'] and canonical_hash(spec) == m['specification_hash'] and
            read(path / 'resolved_design.json') == jobs and canonical_hash(jobs) == m['resolved_design_hash'],
            'Registry design changed')
    require(len(jobs) == m['groups'] and sum(len(arms(j)) for j in jobs) == m['world_records'] and
            len(spec['seeds']) == m['independent_seeds'], 'Registry counts')
    audit, evidence = read(path / 'seed_audit.json'), read(path / 'test_evidence.json')
    _validate_seed_audit(audit, spec['seeds'])
    require(canonical_hash(audit) == m['seed_audit_hash'] and canonical_hash(evidence) == m['test_evidence_hash'],
            'Frozen readiness evidence changed')
    _test_evidence(evidence, path / 'tests.log', m['extension_sha256'], m['dependency_sha256'], m['test_source_sha256'])
    _benchmark_evidence(read(path / 'benchmark.json'), spec, m['extension_sha256'], m['dependency_sha256'])
    require(sha256(path / 'protocol.md') == m['protocol_hash'] and
            sha256(path / 'benchmark.json') == m['benchmark_hash'], 'Protocol or preflight identity mismatch')
    expected = {'manifest.json', 'configuration.json', 'resolved_design.json', 'protocol.md',
                'test_evidence.json', 'tests.log', 'seed_audit.json', 'benchmark.json',
                'original_manifest.json', 'original_inventory.json'} | {'source_snapshot/' + p for p in sources}
    require(set(read(path / 'artifact_hashes.json')) == expected, 'Unexpected registry artifact set')
    require(sha256(path / 'artifact_hashes.json') == digest, 'Registry changed during validation')
    return {'status': 'passed', 'registry_hash': sha256(path / 'manifest.json'),
            'inventory_hash': digest, 'source_hash': m['source_hash'],
            'extension_source_hash': m['extension_source_hash'], 'dependency_source_hash': m['dependency_source_hash'],
            'specification_hash': m['specification_hash']}


@lru_cache(maxsize=4)
def _validated_design(path_name, digest):
    path = Path(path_name)
    gate = validate_registry(path)
    require(gate['inventory_hash'] == digest, 'Registry changed while building authorization')
    return gate, read(path/'manifest.json'), {
        j['group_id']: canonical_hash(j) for j in read(path/'resolved_design.json')}


def authorize_job(registry_path, job, expected_hash):
    # Every call rehashes all bytes and live dependencies. Only semantic parsing
    # of the already verified immutable design is cached, not the integrity check.
    path = Path(registry_path).resolve()
    digest, _ = check_inventory(path)
    gate, manifest, jobs = _validated_design(str(path), digest)
    require(extension_inventory() == manifest['extension_sha256'] and
            dependency_inventory() == manifest['dependency_sha256'] and
            test_inventory() == manifest['test_source_sha256'], 'Live source changed after authorization')
    require(np.__version__ == manifest['numpy_version'] and platform.python_version() == manifest['python_version'],
            'Runtime version changed after authorization')
    require(source_hash() == expected_hash == gate['source_hash'], 'Physical source mismatch')
    require(jobs.get(job['group_id']) == canonical_hash(job), 'Unregistered job')
    return gate
