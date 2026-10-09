from pathlib import Path
from datetime import datetime, timezone
import csv
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from abm_jasss.research_world import canonical_hash, jsonable, source_hash
from scripts.formal_artifacts import read, write_json, write_gzip_json, sha256
from scripts.validate_s1_outputs import require

PRIMARY = ('platform_representation_gap', 'perception_error', 'targeting_error_trigger')
AUXILIARY = ('has_response', 'execution_count', 'execution_coverage', 'scheduled_count',
             'pending_count', 'waiting_time', 'response_completion_L', 'exposure_gap',
             'targeting_error_execution', 'final_preference_shift', 'final_trust_mean',
             'max_pending', 'platform_signal_coverage', 'perception_data_coverage')
E2 = {'I00': {}, 'I10': {'pref_info': True}, 'I01': {'rule_info': True},
      'I11': {'pref_info': True, 'rule_info': True}}
E2_CONTRASTS = {'pref_given_rule0': {'I10': 1, 'I00': -1},
                'pref_given_rule1': {'I11': 1, 'I01': -1},
                'rule_given_pref0': {'I01': 1, 'I00': -1},
                'rule_given_pref1': {'I11': 1, 'I10': -1},
                'interaction': {'I11': 1, 'I10': -1, 'I01': -1, 'I00': 1}}
BRANCHES = {'B0': {}, 'B1': {'pref_info': True}, 'B2': {'government_delay': 1},
            'B3': {'response_capacity': 2}, 'B4': {'alpha': 0.0}}

def utc():
    return datetime.now(timezone.utc).isoformat()

def new_directory(path):
    path = Path(path).resolve()
    require(not path.exists(), 'Refusing to overwrite existing output: ' + str(path))
    path.mkdir(parents=True)
    return path

def inventory(path, name='artifact_hashes.json'):
    path = Path(path)
    result = {p.relative_to(path).as_posix(): sha256(p) for p in sorted(path.rglob('*'))
              if p.is_file() and p != path / name}
    write_json(path / name, result)
    return result

def check_inventory(path, name='artifact_hashes.json'):
    path = Path(path).resolve()
    require(not path.is_symlink(), 'Symlink bundle')
    paths = list(path.rglob('*'))
    require(not any(p.is_symlink() for p in paths), 'Symlink artifact')
    recorded = read(path / name)
    actual = {p.relative_to(path).as_posix(): p for p in paths if p.is_file() and p != path / name}
    require(set(recorded) == set(actual), 'Inventory file set changed')
    for key, value in recorded.items():
        require(sha256(actual[key]) == value, 'Artifact hash changed: ' + key)
    return sha256(path / name), len(recorded)

def write_csv(path, rows):
    rows = list(rows)
    require(bool(rows), 'Empty CSV')
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with Path(path).open('x', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                        for k, v in row.items()})

def arms(job):
    return [('E2', a, x) for a, x in E2.items()] + [
        ('E4', a, x) for a, x in job['branches'].items()] + [
        ('E3_closed', a, x) for a, x in job['closed'].items()] + [
        ('E3_replay', 'delay' + str(d), {'government_delay': d}) for d in job['replay_delays']]

def contrasts(variant):
    result = {'E2': E2_CONTRASTS,
              'E4': {a: {a: 1, 'B0': -1} for a in variant['branches'] if a != 'B0'}}
    if variant['closed']:
        result['E3_closed'] = {a: {a: 1, 'baseline': -1} for a in variant['closed']}
    if variant['replay_delays']:
        result['E3_replay'] = {'delay3': {'delay3': 1, 'delay0': -1}}
    return result
