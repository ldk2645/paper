"""Promote an accepted repair after the original process exits, then recover."""
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
CANDIDATE = ROOT / 'formal_repair_20261003'
ORIGINAL = ROOT / 'outputs/formal_e2_e4_20261003'
ORIGINAL_EXECUTION = ROOT / 'outputs/formal_execution_20261003'
REGISTRY_NAME = 'formal_registry_repair_20261003'
FREEZE_NAME = 'formal_repair_freeze_acceptance_20261003'
REGISTRY = ROOT / 'outputs' / REGISTRY_NAME
BATCH = ROOT / 'outputs/formal_e2_e4_repaired_20261003'
ANALYSIS = ROOT / 'outputs/formal_e2_e4_repaired_20261003_analysis'
PRESENTATION = ROOT / 'outputs/formal_e2_e4_repaired_20261003_report'
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
    assert all(not p.exists() for p in (REGISTRY, ROOT / 'outputs' / FREEZE_NAME, BATCH, ANALYSIS, PRESENTATION))
    frozen = CANDIDATE / 'outputs' / REGISTRY_NAME
    freeze_evidence = CANDIDATE / 'outputs' / FREEZE_NAME
    verify_inventory(freeze_evidence, 'evidence_hashes.json')
    accepted = read(freeze_evidence / 'acceptance.json')
    assert accepted['status'] == 'passed' and accepted['models_executed'] == 0
    assert digest(frozen / 'manifest.json') == accepted['registry_hash']
    repair = read(frozen / 'manifest.json')
    context = read(frozen / 'repair_context.json')
    original_registry = ROOT / 'outputs/formal_registry_20261003'
    parent = read(original_registry / 'manifest.json')
    assert context['parent_registry_hash'] == digest(original_registry / 'manifest.json')
    assert context['additional_independent_samples'] == 0
    write(EVIDENCE / 'launch.json', {'stage': 'formal_repair_execution',
        'started_at': datetime.now(timezone.utc).isoformat(), 'wrapper_hash': digest(__file__),
        'parent_registry_hash': context['parent_registry_hash'], 'repair_registry_hash': accepted['registry_hash'],
        'source_hash': repair['source_hash'], 'source_batch': str(ORIGINAL),
        'candidate_project': str(CANDIDATE), 'workers': WORKERS, 'additional_independent_samples': 0})
    commands = [command('candidate_plan', [sys.executable, '-B', str(CANDIDATE / 'scripts/run_formal_study.py'),
        'plan', str(frozen)], cwd=CANDIDATE, json_name='candidate_plan.json')]
    assert read(EVIDENCE / 'candidate_plan.json')['status'] == 'ready'
    print('WAIT original batch finalization; active original source stays unchanged', flush=True)
    while not (ORIGINAL_EXECUTION / 'evidence_hashes.json').exists():
        time.sleep(10)
    verify_inventory(ORIGINAL_EXECUTION, 'evidence_hashes.json')
    original_result = read(ORIGINAL_EXECUTION / 'run_result.json')
    assert isinstance(original_result['returncode'], int)
    # subprocess.run has returned, so the original CLI and its joined pool have
    # exited. Its wrapper uses only stdlib and has finalized all external evidence.
    assert read(ORIGINAL / 'manifest.json')['status'] in ('complete', 'failed')
    assert (ORIGINAL / 'artifact_hashes.json').is_file()
    before = sources(ROOT)
    assert before == parent['source_sha256'], 'Main source changed while original batch ran'
    assert sources(CANDIDATE) == repair['source_sha256'], 'Candidate changed since repair freeze'
    changed = sorted(name for name, value in repair['source_sha256'].items() if before.get(name) != value)
    assert changed == context['changed_source_paths'], 'Promotion source differences disagree with freeze'
    for name in changed:
        destination = (ROOT / name).resolve()
        assert destination.is_relative_to(ROOT) and Path(name).parts[0] in ('scripts', 'tests')
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(CANDIDATE / name, destination)
        assert digest(destination) == repair['source_sha256'][name]
    documents = []
    for name, value in repair['document_sha256'].items():
        assert digest(CANDIDATE / name) == value
        destination = (ROOT / name).resolve()
        assert destination.is_relative_to(ROOT)
        if destination.exists():
            assert digest(destination) == value, 'Existing frozen contract changed: ' + name
        else:
            assert name == repair['protocol_path'], 'Unexpected new contract: ' + name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(CANDIDATE / name, destination)
            documents.append(name)
    assert sources(ROOT) == repair['source_sha256'], 'Promoted source does not match repair freeze'
    shutil.copytree(frozen, REGISTRY)
    shutil.copytree(freeze_evidence, ROOT / 'outputs' / FREEZE_NAME)
    write(EVIDENCE / 'promotion.json', {'completed_at': datetime.now(timezone.utc).isoformat(),
        'changed_source_paths': changed, 'new_protocol_paths': documents,
        'before_source_sha256': before, 'after_source_sha256': sources(ROOT),
        'parent_source_archive': str(original_registry / 'source_snapshot'),
        'original_run_result_hash': digest(ORIGINAL_EXECUTION / 'run_result.json'),
        'original_batch_status': read(ORIGINAL / 'manifest.json')['status'],
        'repair_registry_hash': digest(REGISTRY / 'manifest.json')})
    base = [sys.executable, '-B', str(ROOT / 'scripts/run_formal_study.py')]
    commands.append(command('promoted_plan', base + ['plan', str(REGISTRY)], json_name='promoted_plan.json'))
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
    write(EVIDENCE / 'acceptance.json', {'status': 'passed', 'stage': 'formal_repaired_execution_and_analysis',
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
