"""Run the registered pilot, full tests, read-only acceptance and planning report."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from abm_jasss.research_cli import require, write_json, file_hash


def execute(config, prefix, workers):
    outputs = {name: ROOT / 'outputs' / f'{prefix}_{name}'
               for name in ('initial', 'expansion', 'acceptance', 'planning')}
    require(all(not path.exists() for path in outputs.values()), 'Pilot prefix already exists')
    acceptance = outputs['acceptance']
    acceptance.mkdir(parents=True)
    commands = []

    def command(name, arguments):
        argv = [sys.executable, '-B', *map(str, arguments)]
        print(f'START {name}', flush=True)
        start = time.monotonic()
        with (acceptance / f'{name}.log').open('x', encoding='utf-8', newline='\n') as log:
            completed = subprocess.run(argv, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                       env=None, check=False)
        evidence = {'name': name, 'command': argv, 'cwd': str(ROOT), 'returncode': completed.returncode,
                    'elapsed_seconds': time.monotonic() - start,
                    'log_sha256': file_hash(acceptance / f'{name}.log')}
        commands.append(evidence)
        write_json(acceptance / f'{name}_command.json', evidence)
        require(completed.returncode == 0, f'{name} failed; inspect {acceptance / (name + ".log")}')
        print(f'PASS {name}: {evidence["elapsed_seconds"]:.1f}s', flush=True)

    command('tests', ['-m', 'unittest', 'discover', '-s', 'tests', '-v'])
    for wave in ('initial', 'expansion'):
        command(wave, ['scripts/run_precision_pilot.py', '--config', config,
                      '--output', outputs[wave], '--wave', wave, '--workers', workers])
    for wave in ('initial', 'expansion'):
        name = 'validate_' + wave
        command(name, ['scripts/validate_precision_pilot.py', outputs[wave], '--workers', workers])
        report = json.loads((acceptance / f'{name}.log').read_text(encoding='utf-8-sig'))
        require(report['status'] == 'passed', f'{name} did not pass')
        write_json(acceptance / f'{name}.json', report)
    command('analysis', ['scripts/analyze_precision_pilot.py', outputs['initial'], outputs['expansion'],
                        '--output', outputs['planning'],
                        '--validation-initial', acceptance / 'validate_initial.json',
                        '--validation-expansion', acceptance / 'validate_expansion.json'])
    write_json(acceptance / 'acceptance.json', {
        'status': 'passed', 'stage': 'precision_pilot', 'formal_ready': False,
        'completed_at': datetime.now(timezone.utc).isoformat(), 'commands': commands,
        'outputs': {name: str(path) for name, path in outputs.items()},
        'scope': 'Independent pilot and approximate sample-size planning; formal design is not released'})
    write_json(acceptance / 'evidence_hashes.json', {p.name: file_hash(p)
               for p in sorted(acceptance.iterdir()) if p.is_file()})
    print(f'COMPLETE {outputs["planning"]}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='configs/precision_pilot_20260930.json')
    parser.add_argument('--prefix', default='precision_pilot_20260930')
    parser.add_argument('--workers', type=int, default=3)
    args = parser.parse_args()
    execute(args.config, args.prefix, args.workers)
