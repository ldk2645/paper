"""Retry the already frozen v2 recovery under a Windows service-owned task."""
from datetime import datetime, timezone
import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = Path(__file__).resolve().parent
CANDIDATE = ROOT / 'formal_repair_resume_20261003'
ORIGINAL = ROOT / 'outputs/formal_e2_e4_20261003'
ORIGINAL_EXECUTION = ROOT / 'outputs/formal_execution_20261003'
REGISTRY_NAME = 'formal_registry_repair_v2_20261003'
FREEZE_NAME = 'formal_repair_v2_freeze_acceptance_20261003'
REGISTRY = ROOT / 'outputs' / REGISTRY_NAME
BATCH = ROOT / 'outputs/formal_e2_e4_repaired_v2_20261004'
ANALYSIS = ROOT / 'outputs/formal_e2_e4_repaired_v2_20261004_analysis'
PRESENTATION = ROOT / 'outputs/formal_e2_e4_repaired_v2_20261004_report'
WORKERS = 12


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            value.update(chunk)
    return value.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def sources(root):
    files = [p for folder in ('abm_jasss', 'scripts', 'tests') for p in sorted((root / folder).rglob('*.py'))]
    files.append(root / 'requirements.txt')
    return {p.relative_to(root).as_posix(): digest(p) for p in files}


def verify_inventory(folder, name='artifact_hashes.json'):
    inventory = read(folder / name)
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()}
    assert set(inventory) == actual - {name}, 'Evidence inventory differs: ' + str(folder)
    assert all(digest(folder / path) == value for path, value in inventory.items()), 'Evidence changed'


def command(stage, argv, cwd=ROOT, json_name=None):
    started = time.monotonic()
    write(EVIDENCE / f'{stage}_started.json', {'stage': stage, 'command': argv, 'cwd': str(cwd),
        'started_at': datetime.now(timezone.utc).isoformat()})
    print('START ' + stage, flush=True)
    path = EVIDENCE / f'{stage}.log'
    with path.open('x', encoding='utf-8', newline='\n') as log:
        result = subprocess.run(argv, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, check=False)
    report = {'stage': stage, 'command': argv, 'returncode': result.returncode,
        'elapsed_seconds': time.monotonic() - started, 'log_sha256': digest(path),
        'completed_at': datetime.now(timezone.utc).isoformat()}
    write(EVIDENCE / f'{stage}_result.json', report)
    if result.returncode:
        raise RuntimeError(stage + ' failed; inspect ' + str(path))
    if json_name:
        write(EVIDENCE / json_name, json.loads(path.read_text(encoding='utf-8-sig')))
    print(f'PASS {stage}: {report["elapsed_seconds"]:.1f}s', flush=True)
    return report


def main():
    assert not (EVIDENCE / 'launch.json').exists(), 'Execution already launched'
    assert all(not p.exists() for p in (BATCH, ANALYSIS, PRESENTATION)), 'Retry outputs must be new'
    freeze_evidence = ROOT / 'outputs' / FREEZE_NAME
    verify_inventory(freeze_evidence, 'evidence_hashes.json')
    accepted = read(freeze_evidence / 'acceptance.json')
    assert accepted['status'] == 'passed' and accepted['models_executed'] == 0 and accepted['tests_run'] == 279
    assert digest(REGISTRY / 'manifest.json') == accepted['registry_hash']
    repair, context = read(REGISTRY / 'manifest.json'), read(REGISTRY / 'repair_context.json')
    assert sources(ROOT) == repair['source_sha256'], 'Main source differs from frozen v2'
    original_registry = ROOT / 'outputs/formal_registry_20261003'
    assert context['parent_registry_hash'] == digest(original_registry / 'manifest.json')
    assert context['additional_independent_samples'] == 0
    verify_inventory(ORIGINAL_EXECUTION, 'evidence_hashes.json')
    original = read(ORIGINAL / 'manifest.json')
    assert original['status'] == 'failed' and original['completed_groups'] == 1183 and original['failed_groups'] == 1
    interruption = ROOT / 'outputs/formal_repair_v2_interruption_20261004'
    verify_inventory(interruption)
    write(EVIDENCE / 'launch.json', {'stage': 'formal_repair_v2_retry_execution',
        'started_at': datetime.now(timezone.utc).isoformat(), 'wrapper_hash': digest(__file__),
        'parent_registry_hash': context['parent_registry_hash'], 'repair_registry_hash': accepted['registry_hash'],
        'source_hash': repair['source_hash'], 'source_batch': str(ORIGINAL),
        'workers': WORKERS, 'additional_independent_samples': 0,
        'software_revision': 'unchanged_frozen_v2', 'interruption_evidence_hash': digest(interruption / 'artifact_hashes.json')})
    commands = []
    base = [sys.executable, '-B', str(ROOT / 'scripts/run_formal_study.py')]
    commands.append(command('frozen_plan', base + ['plan', str(REGISTRY)], json_name='frozen_plan.json'))
    commands.append(command('recover', [sys.executable, '-B', str(ROOT / 'scripts/recover_formal_study.py'),
        str(ORIGINAL), str(REGISTRY), '--output', str(BATCH), '--workers', str(WORKERS)]))
    commands.append(command('validate', base + ['validate', str(BATCH), '--workers', str(WORKERS)],
                            json_name='validation.json'))
    validation = read(EVIDENCE / 'validation.json')
    assert validation['status'] == 'passed' and validation['read_only'] is True
    commands.append(command('analyze', base + ['analyze', str(BATCH), '--output', str(ANALYSIS),
        '--validation', str(EVIDENCE / 'validation.json')], json_name='analysis.json'))
    analysis = read(EVIDENCE / 'analysis.json')
    assert analysis['semantic_validation_complete'] is True and analysis['additional_sampling'] is False
    commands.append(command('report', [sys.executable, '-B',
        str(ROOT / 'outputs/formal_reporting_tools_20261003/report_formal_results.py'),
        str(ANALYSIS), str(REGISTRY), '--output', str(PRESENTATION)]))
    verify_inventory(ANALYSIS)
    verify_inventory(PRESENTATION)
    manifest, recovery = read(BATCH / 'manifest.json'), read(BATCH / 'recovery_provenance.json')
    assert recovery['planned_reused_groups'] == 1183 and recovery['planned_rerun_groups'] == 1
    assert recovery['completed_groups'] == 1184 and recovery['failed_groups'] == 0
    assert recovery['additional_independent_samples'] == 0 and recovery['source_status_is_not_rewritten'] is True
    assert manifest['status'] == 'complete' and manifest['failed_groups'] == 0
    assert manifest['completed_groups'] == validation['groups'] == 1184
    assert manifest['complete_records'] == validation['world_records'] == 21312
    assert validation['independent_seeds'] == 1000 and read(BATCH / 'failures.json') == []
    assert len(read(BATCH / 'statistical_records.json')) == len(read(BATCH / 'auxiliary_records.json')) == 22496
    rows = {}
    for name in ('primary', 'auxiliary'):
        with (ANALYSIS / f'{name}.csv').open(encoding='utf-8', newline='') as stream:
            rows[name] = len(list(csv.DictReader(stream)))
    assert rows == {'primary': 102, 'auxiliary': 532}
    write(EVIDENCE / 'acceptance.json', {'status': 'passed', 'stage': 'formal_repaired_v2_retry_execution_and_analysis',
        'completed_at': datetime.now(timezone.utc).isoformat(), 'commands': commands,
        'registry_hash': digest(REGISTRY / 'manifest.json'), 'source_hash': manifest['source_hash'],
        'batch_id': manifest['batch_id'], 'batch_manifest_hash': digest(BATCH / 'manifest.json'),
        'batch_inventory_hash': digest(BATCH / 'artifact_hashes.json'),
        'analysis_inventory_hash': digest(ANALYSIS / 'artifact_hashes.json'),
        'report_inventory_hash': digest(PRESENTATION / 'artifact_hashes.json'),
        'validation_report_hash': digest(EVIDENCE / 'validation.json'),
        'groups': 1184, 'world_records': 21312, 'independent_seeds': 1000, 'table_rows': rows,
        'reused_groups': recovery['planned_reused_groups'], 'rerun_groups': recovery['planned_rerun_groups'],
        'additional_independent_samples': 0, 'original_status_retained': recovery['source_status']})
    print('COMPLETE repaired formal batch, validation, analysis and figures', flush=True)


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
