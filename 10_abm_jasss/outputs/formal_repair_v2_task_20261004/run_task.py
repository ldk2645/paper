"""Service-owned, windowless launcher for the one authorized formal retry."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

HERE = Path(__file__).resolve().parent


def write(name, value):
    with (HERE / name).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, ensure_ascii=True)
        stream.write('\n')


def main():
    config = json.loads((HERE / 'task_configuration.json').read_text(encoding='utf-8'))
    wrapper = Path(config['wrapper'])
    assert hashlib.sha256(wrapper.read_bytes()).hexdigest() == config['wrapper_sha256']
    assert wrapper.resolve().is_relative_to(Path(config['root']).resolve())
    registry_manifest = Path(config['root']) / 'outputs/formal_registry_repair_v2_20261003/manifest.json'
    assert hashlib.sha256(registry_manifest.read_bytes()).hexdigest() == config['registry_hash']
    command = [config['python'], '-B', str(wrapper)]
    write('process.json', {'started_at': datetime.now(timezone.utc).isoformat(),
        'runner_pid': os.getpid(), 'parent_pid': os.getppid(), 'runner_executable': sys.executable,
        'task_name': config['task_name'], 'command': command, 'working_directory': config['root'],
        'wrapper_sha256': config['wrapper_sha256']})
    with (HERE / 'stdout.log').open('x', encoding='utf-8') as out, (HERE / 'stderr.log').open('x', encoding='utf-8') as err:
        child = subprocess.Popen(command, cwd=config['root'], stdout=out, stderr=err,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        write('child.json', {'pid': child.pid, 'started_at': datetime.now(timezone.utc).isoformat()})
        code = child.wait()
    write('task_result.json', {'returncode': code, 'finished_at': datetime.now(timezone.utc).isoformat()})
    # This task has no timed/repeating trigger. Also disable manual relaunch after
    # its one invocation finishes; all existing artifacts remain untouched.
    disabled = subprocess.run(['schtasks.exe', '/Change', '/TN', config['task_name'], '/DISABLE'],
        capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, check=False)
    write('disable_result.json', {'returncode': disabled.returncode,
        'stdout': disabled.stdout.decode(errors='replace'), 'stderr': disabled.stderr.decode(errors='replace')})
    return code


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        if not (HERE / 'launcher_failure.json').exists():
            write('launcher_failure.json', {'traceback': traceback.format_exc(),
                'failed_at': datetime.now(timezone.utc).isoformat()})
        raise
