"""Read a supplement pipeline's persisted state without changing artifacts."""
import argparse
import json
from pathlib import Path


def status(path):
    root = Path(path).resolve()
    result = {'path': str(root), 'status': 'not_started', 'read_only': True}
    def read(name):
        target = root / name
        return json.loads(target.read_text(encoding='utf-8')) if target.is_file() else None
    acceptance = read('acceptance.json')
    if acceptance is not None:
        return dict(result, status=acceptance['status'], acceptance=acceptance)
    launch = read('batch/launch.json')
    if launch is None:
        return result
    result.update(status='started_without_final_acceptance', expected_groups=launch['expected_groups'],
                  batch_id=launch['batch_id'], started_at=launch['started_at'],
                  completed_groups=0, failed_groups=0)
    progress = root / 'batch/progress.jsonl'
    if progress.is_file():
        with progress.open(encoding='utf-8') as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    result['partial_last_progress_line'] = True
                    continue
                result['completed_groups' if row['status'] == 'complete' else 'failed_groups'] += 1
                result['last_progress'] = {k: row[k] for k in ('at', 'status', 'group_id')}
    for stage in ('run', 'validate', 'analyze', 'report'):
        completion = read(stage+'_completion.json')
        if completion is not None:
            result['last_completed_stage'] = stage
            result['last_stage_completed_at'] = completion['completed_at']
    result['live_process_verified'] = False
    result['note'] = 'Persisted progress alone cannot distinguish running from interrupted; check the launch PID separately.'
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('pipeline')
    args = parser.parse_args()
    print(json.dumps(status(args.pipeline), ensure_ascii=False, indent=2))
