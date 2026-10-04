"""Read execution progress only; never touch simulation artifacts."""
from datetime import datetime, timezone
from pathlib import Path
import json
import re
import time

folder = Path(__file__).resolve().parent
while True:
    phase = next((name for name in ('analyze', 'validate', 'run', 'plan')
                  if (folder / f'{name}_started.json').exists()), 'starting')
    log = (folder / 'run.log').read_text(encoding='utf-8-sig') if (folder / 'run.log').exists() else ''
    matches = re.findall(r'formal: (\d+)/1184 complete', log)
    report = {'time': datetime.now(timezone.utc).isoformat(timespec='seconds'),
              'phase': phase, 'completed_groups': int(matches[-1]) if matches else 0,
              'total_groups': 1184, 'failed_groups_logged': log.count('formal: FAILED ')}
    done = (folder / 'acceptance.json').exists() or (folder / 'failure.json').exists()
    if done:
        report['pipeline_status'] = 'passed' if (folder / 'acceptance.json').exists() else 'failed'
    print(json.dumps(report), flush=True)
    if done:
        break
    time.sleep(45)
