"""Read-only observer of the detached formal pipeline; not a release gate."""
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'outputs/formal_repair_v2_retry_execution_20261004'
BATCH = ROOT / 'outputs/formal_e2_e4_repaired_v2_20261004'


class ProcessEntry(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('usage', wintypes.DWORD),
        ('pid', wintypes.DWORD), ('heap', ctypes.c_size_t), ('module', wintypes.DWORD),
        ('threads', wintypes.DWORD), ('parent', wintypes.DWORD),
        ('priority', wintypes.LONG), ('flags', wintypes.DWORD),
        ('name', wintypes.WCHAR * 260)]


class IO(ctypes.Structure):
    _fields_ = [(key, ctypes.c_ulonglong) for key in
        ('read_operations', 'write_operations', 'other_operations',
         'read_bytes', 'write_bytes', 'other_bytes')]


def processes():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    for name in ('Process32FirstW', 'Process32NextW'):
        method = getattr(kernel, name)
        method.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
        method.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessIoCounters.argtypes = [wintypes.HANDLE, ctypes.POINTER(IO)]
    kernel.GetProcessIoCounters.restype = wintypes.BOOL
    handle = kernel.CreateToolhelp32Snapshot(2, 0)
    if handle == ctypes.c_void_p(-1).value:
        return {'unavailable': ctypes.get_last_error()}
    entry, records = ProcessEntry(), []
    entry.size = ctypes.sizeof(entry)
    success = kernel.Process32FirstW(handle, ctypes.byref(entry))
    while success:
        if entry.name.lower() in ('python.exe', 'pythonw.exe') and entry.pid != os.getpid():
            counters, process = IO(), kernel.OpenProcess(0x1000, False, entry.pid)
            record = {'pid': entry.pid, 'parent_pid': entry.parent, 'threads': entry.threads}
            if process:
                if kernel.GetProcessIoCounters(process, ctypes.byref(counters)):
                    record.update({name: getattr(counters, name) for name, _ in IO._fields_})
                kernel.CloseHandle(process)
            records.append(record)
        success = kernel.Process32NextW(handle, ctypes.byref(entry))
    kernel.CloseHandle(handle)
    identity = Path(__file__).resolve().parent / 'process.json'
    if not identity.exists():
        return []
    task_pid = json.loads(identity.read_text(encoding='utf-8'))['runner_pid']
    descendants = {task_pid}
    while True:
        expanded = descendants | {item['pid'] for item in records if item['parent_pid'] in descendants}
        if expanded == descendants:
            break
        descendants = expanded
    return [item for item in records if item['pid'] in descendants]


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


stages = {}
for stage in ('frozen_plan', 'recover', 'validate', 'analyze', 'report'):
    result = EVIDENCE / (stage + '_result.json')
    if result.exists():
        value = read(result)
        stages[stage] = {'returncode': value['returncode'], 'seconds': round(value['elapsed_seconds'], 1)}
    elif (EVIDENCE / (stage + '_started.json')).exists():
        stages[stage] = 'running_or_interrupted'
logs = {}
for name in ('recover', 'validate', 'analyze', 'report'):
    path = EVIDENCE / (name + '.log')
    if path.exists():
        lines = path.read_text(encoding='utf-8-sig', errors='replace').splitlines()
        logs[name] = [line[:300] for line in lines[-2:]]
value = {'at': datetime.now(timezone.utc).isoformat(), 'stages': stages,
    'complete_group_files': len(list((BATCH / 'groups').glob('*.json'))),
    'recovery_proof_files': len(list((BATCH / 'recovery_groups').glob('*.json'))),
    'batch_finalized': (BATCH / 'artifact_hashes.json').exists(), 'logs': logs,
    'python_processes': processes()}
for name in ('acceptance', 'failure'):
    path = EVIDENCE / (name + '.json')
    if path.exists():
        value[name] = read(path)
print(json.dumps(value, ensure_ascii=True))
