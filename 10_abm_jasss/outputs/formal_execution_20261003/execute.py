"""Execute the unchanged frozen CLI and retain external execution evidence."""
from datetime import datetime, timezone
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = Path(__file__).resolve().parent
REGISTRY = ROOT / 'outputs/formal_registry_20261003'
BATCH = ROOT / 'outputs/formal_e2_e4_20261003'
ANALYSIS = ROOT / 'outputs/formal_e2_e4_20261003_analysis'
WORKERS = 12


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def inventory(folder):
    files = {p.relative_to(folder).as_posix(): p for p in folder.rglob('*') if p.is_file()}
    expected = read(folder / 'artifact_hashes.json')
    assert set(expected) == set(files) - {'artifact_hashes.json'}, 'Analysis file inventory differs'
    assert all(digest(files[name]) == value for name, value in expected.items()), 'Analysis hash differs'


def main():
    assert not BATCH.exists() and not ANALYSIS.exists(), 'Formal output already exists'
    assert not (EVIDENCE / 'launch.json').exists(), 'Execution evidence already exists'
    registry_manifest = read(REGISTRY / 'manifest.json')
    write(EVIDENCE / 'launch.json', {
        'stage': 'formal_execution', 'started_at': datetime.now(timezone.utc).isoformat(),
        'registry': str(REGISTRY), 'registry_hash': digest(REGISTRY / 'manifest.json'),
        'source_hash': registry_manifest['source_hash'], 'workers': WORKERS,
        'batch': str(BATCH), 'analysis': str(ANALYSIS), 'wrapper_hash': digest(__file__),
        'resource_preflight': {'logical_cpus': 20, 'memory_total_bytes': 33597796352,
            'memory_available_bytes': 14607740928, 'disk_free_bytes': 534419972096},
        'sample_sizes': {'0.25': 184, '0.75': 1000}, 'additional_sampling': False})
    base = [sys.executable, '-B', str(ROOT / 'scripts/run_formal_study.py')]
    commands = [
        ('plan', base + ['plan', str(REGISTRY)]),
        ('run', base + ['run', str(REGISTRY), '--output', str(BATCH), '--workers', str(WORKERS)]),
        ('validate', base + ['validate', str(BATCH), '--workers', str(WORKERS)]),
        ('analyze', base + ['analyze', str(BATCH), '--output', str(ANALYSIS),
                          '--validation', str(EVIDENCE / 'validation.json')]),
    ]
    results = []
    for stage, command in commands:
        started = time.monotonic()
        print(f'START {stage}', flush=True)
        write(EVIDENCE / f'{stage}_started.json', {
            'command': command, 'cwd': str(ROOT), 'started_at': datetime.now(timezone.utc).isoformat()})
        log_path = EVIDENCE / f'{stage}.log'
        with log_path.open('x', encoding='utf-8', newline='\n') as log:
            process = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=False)
        result = {'stage': stage, 'command': command, 'returncode': process.returncode,
                  'elapsed_seconds': time.monotonic() - started, 'log_sha256': digest(log_path),
                  'finished_at': datetime.now(timezone.utc).isoformat()}
        results.append(result)
        write(EVIDENCE / f'{stage}_result.json', result)
        if process.returncode != 0:
            raise RuntimeError(f'{stage} failed; inspect {log_path}')
        if stage in ('plan', 'validate', 'analyze'):
            report = json.loads(log_path.read_text(encoding='utf-8-sig'))
            if stage == 'analyze':
                assert report['semantic_validation_complete'] is True and report['additional_sampling'] is False, report
            else:
                assert report['status'] in ('ready', 'passed'), report
            write(EVIDENCE / ('validation.json' if stage == 'validate' else f'{stage}.json'), report)
        print(f'PASS {stage}: {result["elapsed_seconds"]:.1f}s', flush=True)
    manifest, validation = read(BATCH / 'manifest.json'), read(EVIDENCE / 'validation.json')
    assert manifest['status'] == 'complete' and manifest['failed_groups'] == 0
    assert manifest['completed_groups'] == validation['groups'] == 1184
    assert manifest['complete_records'] == validation['world_records'] == 21312
    assert validation['independent_seeds'] == 1000 and read(BATCH / 'failures.json') == []
    assert len(read(BATCH / 'statistical_records.json')) == 22496
    assert len(read(BATCH / 'auxiliary_records.json')) == 22496
    inventory(ANALYSIS)
    counts = {}
    for name in ('primary', 'auxiliary'):
        with (ANALYSIS / f'{name}.csv').open(encoding='utf-8', newline='') as stream:
            counts[name] = len(list(csv.DictReader(stream)))
    assert counts == {'primary': 102, 'auxiliary': 532}, counts
    write(EVIDENCE / 'acceptance.json', {
        'status': 'passed', 'stage': 'formal_execution_and_analysis', 'formal_ready': True,
        'completed_at': datetime.now(timezone.utc).isoformat(), 'commands': results,
        'registry_hash': digest(REGISTRY / 'manifest.json'),
        'source_hash': manifest['source_hash'], 'batch_id': manifest['batch_id'],
        'batch_manifest_hash': digest(BATCH / 'manifest.json'),
        'batch_inventory_hash': digest(BATCH / 'artifact_hashes.json'),
        'analysis_manifest_hash': digest(ANALYSIS / 'analysis_manifest.json'),
        'analysis_inventory_hash': digest(ANALYSIS / 'artifact_hashes.json'),
        'validation_report_hash': digest(EVIDENCE / 'validation.json'),
        'groups': 1184, 'independent_seeds': 1000, 'world_records': 21312,
        'statistical_arms': 22496, 'table_rows': counts, 'additional_sampling': False})
    print('COMPLETE formal execution, validation and analysis', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        if not (EVIDENCE / 'failure.json').exists():
            write(EVIDENCE / 'failure.json', {'status': 'failed', 'traceback': traceback.format_exc()})
        raise
    finally:
        if not (EVIDENCE / 'evidence_hashes.json').exists():
            write(EVIDENCE / 'evidence_hashes.json', {p.name: digest(p)
                  for p in sorted(EVIDENCE.iterdir()) if p.is_file()})
