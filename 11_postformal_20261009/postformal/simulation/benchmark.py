"""Timing-only development runs; independent of registered supplement seeds."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from postformal.simulation.common import *
from abm_jasss.research_config import ResearchConfig
from abm_jasss.research_world import ResearchWorld
import argparse
import gzip
import time

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output')
    args = parser.parse_args()
    out = new_directory(args.output)
    base = read(ROOT / 'configs/formal_design_20261003.json')['model']
    cases = [('baseline', {}), ('grid6_reference8', {'inference_grid': 6, 'reference_agents': 8}),
             ('reference16', {'reference_agents': 16}), ('population200', {'n_agents': 200}),
             ('horizon450', {'steps': 450, 'completion_start': 300, 'completion_end': 429})]
    report = {'stage': 'timing_development_only', 'started_at': utc(), 'source_hash': source_hash(),
              'seed': 920001, 'outcomes_inspected': False, 'cases': []}
    for name, change in cases:
        cfg = ResearchConfig.from_dict(dict(base, alpha=.75, **change))
        start = time.perf_counter()
        world = ResearchWorld(cfg, report['seed']).run()
        simulated = time.perf_counter() - start
        raw = json.dumps(world.snapshot(), ensure_ascii=False, allow_nan=False).encode()
        record = {'variant': name, 'seconds_simulate': simulated, 'ticks': cfg.steps,
                  'snapshot_gzip_bytes': len(gzip.compress(raw, compresslevel=1, mtime=0)),
                  'config': cfg.to_dict()}
        report['cases'].append(record)
        write_json(out / (name + '.json'), record)
        print(json.dumps({k: v for k, v in record.items() if k != 'config'}), flush=True)
    report['completed_at'] = utc()
    write_json(out / 'report.json', report)
    inventory(out)

if __name__ == '__main__':
    main()
