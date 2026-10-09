"""Diagnostic-only reproduction of the failing registered I11 endpoint."""
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
import traceback

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import numpy as np
from abm_jasss.research_config import ResearchConfig
from abm_jasss.research_outcomes import DISTANCE_KEYS, summarize_world
from abm_jasss.research_world import ResearchWorld, source_hash
from scripts.formal_registry import validate_registry
from scripts.run_precision_pilot import E2

REGISTRY = ROOT / 'outputs/formal_registry_20261003'
OUTPUT = Path(__file__).resolve().parent / 'i11_distance_inspection'
GROUP_ID = 'a01_seed71100'


def write(name, value):
    with (OUTPUT / name).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def vector_details(value):
    if value is None:
        return None
    return {'values': value, 'sum_builtin': sum(value), 'sum_fsum': math.fsum(value),
            'sum_numpy': float(np.asarray(value).sum()),
            'sum_decimal_of_stored_binary': str(sum(map(Decimal.from_float, value), Decimal(0))),
            'minimum': min(value), 'maximum': max(value),
            'all_finite': all(math.isfinite(v) for v in value)}


def main():
    if OUTPUT.exists():
        raise FileExistsError('Preserve existing diagnostic output')
    gate = validate_registry(REGISTRY)
    jobs = json.loads((REGISTRY / 'resolved_design.json').read_text(encoding='utf-8'))
    job = next(job for job in jobs if job['group_id'] == GROUP_ID)
    config = replace(ResearchConfig.from_dict(job['model']), **E2['I11'])
    OUTPUT.mkdir(exist_ok=False)
    write('diagnostic_manifest.json', {
        'stage': 'failure_diagnostic_only', 'eligible_for_formal_analysis': False,
        'created_at': datetime.now(timezone.utc).isoformat(), 'group_id': GROUP_ID,
        'seed': job['seed'], 'arm': 'I11', 'registry_hash': gate['registry_hash'],
        'source_hash': gate['source_hash'], 'physical_configuration': config.to_dict(),
        'purpose': 'Reproduce registered failing endpoint; no replacement or extra formal sample',
        'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    world = ResearchWorld(config, job['seed']).run()
    snapshot = world.snapshot()
    payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, allow_nan=False,
                         separators=(',', ':')).encode('utf-8')
    with (OUTPUT / 'snapshot.json.gz').open('xb') as stream:
        stream.write(gzip.compress(payload, compresslevel=1, mtime=0))
    outside = []
    for row in world.trajectory:
        for key in DISTANCE_KEYS:
            value = row.get(key)
            if value is None or 0 <= value <= 1:
                continue
            used_id = row['estimate_input_packet_id']
            used = world.packet_index.get(used_id, {}).get('signal')
            estimate = row['P_hat_gov']
            record = {'tick': row['step'], 'metric': key, 'value': value,
                      'value_hex': float(value).hex(), 'excess_above_one': value - 1,
                      'excess_in_ulps_at_one': (value - 1) / math.ulp(1.0),
                      'in_final_window': row['step'] >= config.steps - config.final_window,
                      'estimate_input_packet_id': used_id,
                      'used_public_signal': vector_details(used),
                      'government_estimate': vector_details(estimate),
                      'P_true': vector_details(row['P_true'])}
            if used is not None and estimate is not None:
                record['signal_estimate_tv_numpy'] = float(.5 * np.abs(np.asarray(used) - np.asarray(estimate)).sum())
                record['signal_estimate_tv_fsum'] = .5 * math.fsum(abs(a - b) for a, b in zip(used, estimate))
                record['signal_estimate_tv_decimal_of_binary'] = str(Decimal('.5') * sum(
                    (abs(Decimal.from_float(a) - Decimal.from_float(b)) for a, b in zip(used, estimate)), Decimal(0)))
            outside.append(record)
    try:
        summarize_world(world.trajectory, world.events, config.analysis_config())
        summary_check = {'status': 'unexpectedly_passed'}
    except Exception:
        summary_check = {'status': 'reproduced_failure', 'traceback': traceback.format_exc()}
    assert source_hash() == gate['source_hash'], 'Frozen source changed during diagnostic'
    write('distance_report.json', {'eligible_for_formal_analysis': False,
        'group_id': GROUP_ID, 'seed': job['seed'], 'arm': 'I11', 'ticks_completed': world.tick,
        'snapshot_state_hash': snapshot['state_hash'], 'all_distance_fields_checked': list(DISTANCE_KEYS),
        'out_of_bounds_count': len(outside), 'out_of_bounds': outside, 'summary_check': summary_check})
    write('artifact_hashes.json', {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
          for p in sorted(OUTPUT.iterdir()) if p.is_file()})
    print(json.dumps({'output': str(OUTPUT), 'ticks_completed': world.tick,
                      'out_of_bounds': outside, 'summary_status': summary_check['status'],
                      'eligible_for_formal_analysis': False}, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
