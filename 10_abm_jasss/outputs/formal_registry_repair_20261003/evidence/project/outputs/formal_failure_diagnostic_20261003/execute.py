"""Reproduce one failed registered job; diagnostic data are never formal samples."""
from pathlib import Path
import json
import sys
import traceback

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.formal_runtime import run_group
from scripts.precision_artifacts import read, write_json, sha256

folder = Path(__file__).resolve().parent
registry = ROOT / 'outputs/formal_registry_20261003'
job = next(j for j in read(registry / 'resolved_design.json') if j['group_id'] == 'a01_seed71100')
manifest = read(registry / 'manifest.json')
write_json(folder / 'diagnostic_manifest.json', {
    'stage': 'software_failure_diagnostic', 'eligible_for_formal_analysis': False,
    'original_batch': 'outputs/formal_e2_e4_20261003', 'group_id': job['group_id'],
    'registry_hash': sha256(registry / 'manifest.json'), 'source_hash': manifest['source_hash'],
    'additional_independent_samples': 0, 'purpose': 'Reproduce failure with identical frozen job and source'})
write_json(folder / 'job.json', job)
try:
    result = run_group(job, str(folder / 'diagnostic_raw'), 'diagnostic_a01_seed71100',
                       manifest['source_hash'], str(registry))
    write_json(folder / 'result.json', {'status': 'reproduction_completed', 'result': result})
    print('Registered job completed in diagnostic reproduction', flush=True)
except Exception:
    error = traceback.format_exc()
    write_json(folder / 'failure.json', {'status': 'reproduced_failure', 'traceback': error})
    print(error, flush=True)
    raise
