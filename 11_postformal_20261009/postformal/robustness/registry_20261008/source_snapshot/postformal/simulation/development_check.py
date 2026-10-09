"""Full-arm development timing and read-only reconstruction, never study evidence.

The authorization stub is limited to this development harness and a disjoint
seed. Production run/validate commands continue to require a frozen registry.
No primary contrasts, intervals or p-values are produced by this harness.
"""
import argparse
import time
from unittest.mock import patch
from .common import *
from .registry import resolve, extension_inventory, dependency_inventory
from .runtime import run_group, validate_group
from abm_jasss.research_config import RESEARCH_VERSION


def preflight(configuration, output):
    spec = read(configuration)
    seed = 920101
    require(seed not in spec['seeds'], 'Development seed overlaps proposed study')
    development_spec = dict(spec, phase='development', seeds=[seed])
    jobs = resolve(development_spec)
    out = new_directory(output)
    ext = canonical_hash(extension_inventory())
    dep = canonical_hash(dependency_inventory())
    gate = {'registry_hash': canonical_hash({'development_only': True, 'spec': development_spec}),
            'source_hash': source_hash(), 'extension_source_hash': ext}
    manifest = dict(gate, batch_id='development_'+out.name, registry_path='DEVELOPMENT_ONLY',
                    code_version=RESEARCH_VERSION)
    report = {'stage': 'postformal_development_preflight', 'status': 'running',
              'started_at': utc(), 'seed': seed, 'source_hash': source_hash(),
              'extension_source_hash': ext, 'dependency_source_hash': dep,
              'specification_hash': canonical_hash(spec), 'outcomes_inspected': False,
              'primary_inference_generated': False, 'cases': []}
    write_json(out/'development_configuration.json', development_spec)
    for job in jobs:
        directory = new_directory(out/'groups'/job['group_id'])
        with patch('postformal.simulation.runtime.authorize_job', return_value=gate):
            start = time.perf_counter()
            result = run_group(job, directory, manifest['batch_id'], source_hash(), 'DEVELOPMENT_ONLY')
            run_seconds = time.perf_counter()-start
            before = inventory(directory)
            start = time.perf_counter()
            verified = validate_group(job, directory, manifest, 'DEVELOPMENT_ONLY')
            validation_seconds = time.perf_counter()-start
        require(check_inventory(directory)[1] == len(before), 'Development validator mutated inputs')
        row = {'variant': job['variant'], 'alpha': job['alpha'], 'seed': seed,
               'world_records': result['world_records'], 'trajectory_records': verified['trajectory_records'],
               'run_seconds': run_seconds, 'validation_seconds': validation_seconds,
               'bytes': sum(p.stat().st_size for p in directory.rglob('*') if p.is_file()),
               'read_only_reconstruction': 'passed'}
        report['cases'].append(row)
        print(json.dumps(row), flush=True)
    require(ext == canonical_hash(extension_inventory()) and dep == canonical_hash(dependency_inventory()),
            'Code changed during development preflight')
    report.update(status='passed', completed_at=utc(), study_seed_count=len(spec['seeds']),
                  projected_serial_run_seconds=sum(r['run_seconds'] for r in report['cases'])*len(spec['seeds']),
                  projected_serial_validation_seconds=sum(r['validation_seconds'] for r in report['cases'])*len(spec['seeds']),
                  projected_batch_bytes=sum(r['bytes'] for r in report['cases'])*len(spec['seeds']),
                  projection_limit='One development seed per setting/alpha; no variance or precision estimate; parallel and filesystem overhead not guaranteed')
    write_json(out/'report.json', report)
    inventory(out)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('configuration')
    parser.add_argument('output')
    args = parser.parse_args()
    result = preflight(args.configuration, args.output)
    print(json.dumps({k: v for k, v in result.items() if k != 'cases'}), flush=True)
