"""Record launch configuration checks; this is not scientific acceptance."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ns = {'t': 'http://schemas.microsoft.com/windows/2004/02/mit/task'}
xml = ET.fromstring((HERE / 'registered_task.xml').read_text(encoding='utf-8-sig'))
get = lambda key: xml.findtext(key, namespaces=ns)
assert get('t:Principals/t:Principal/t:LogonType') == 'InteractiveToken'
# LeastPrivilege is the documented default when RunLevel is omitted.
assert get('t:Principals/t:Principal/t:RunLevel') in (None, 'LeastPrivilege')
assert get('t:Settings/t:MultipleInstancesPolicy') == 'IgnoreNew'
assert get('t:Settings/t:ExecutionTimeLimit') == 'PT0S'
triggers = xml.find('t:Triggers', ns)
assert triggers is None or len(triggers) == 0
assert xml.find('t:Settings/t:RestartOnFailure', ns) is None
config = json.loads((HERE / 'task_configuration.json').read_text())
assert get('t:Actions/t:Exec/t:Command') == config['pythonw']
assert get('t:Actions/t:Exec/t:WorkingDirectory') == config['root']
assert hashlib.sha256(Path(config['wrapper']).read_bytes()).hexdigest() == config['wrapper_sha256']
assert hashlib.sha256((ROOT / 'outputs/formal_registry_repair_v2_20261003/manifest.json').read_bytes()).hexdigest() == config['registry_hash']
process = json.loads((HERE / 'process.json').read_text())
child = json.loads((HERE / 'child.json').read_text())
verification = {'status': 'launch_verified_not_scientific_acceptance',
    'observed_at': datetime.now(timezone.utc).isoformat(), 'task_name': config['task_name'],
    'last_observed_task_state': 'Running', 'task_service_query_observed_at': '2026-10-03T16:22:12+00:00',
    'runner_pid': process['runner_pid'], 'runner_parent_pid': process['parent_pid'],
    'runner_parent_name_observed': 'svchost', 'wrapper_pid': child['pid'],
    'logon_type': 'InteractiveToken', 'run_level': 'LeastPrivilege',
    'keep_windows_user_logged_in': True, 'recurring_triggers': 0, 'automatic_retry': False,
    'execution_time_limit': 'PT0S', 'multiple_instances': 'IgnoreNew',
    'frozen_plan_passed': True, 'tests_run_in_reused_freeze': 279,
    'registry_hash': config['registry_hash'], 'formal_analysis_released': False,
    'xml_export_encoding_note': 'Original service export text was saved as UTF-8 with its UTF-16 declaration. Original retained; parsed UTF-8 equivalent saved separately.',
    'source': str(ROOT / 'outputs/formal_e2_e4_20261003'),
    'target': str(ROOT / 'outputs/formal_e2_e4_repaired_v2_20261004')}
assert not (HERE / 'launch_verification.json').exists()
ET.ElementTree(xml).write(HERE / 'registered_task_utf8.xml', encoding='utf-8', xml_declaration=True)
(HERE / 'launch_verification.json').write_text(json.dumps(verification, indent=2) + '\n', encoding='utf-8')
names = ('launch_verification.json', 'check_launch.py', 'task_configuration.json', 'register_task.ps1',
    'run_task.py', 'registered_task.xml', 'registered_task_utf8.xml', 'registration.json', 'process.json', 'child.json')
(HERE / 'launch_verification_hashes.json').write_text(json.dumps({name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
    for name in names}, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'status': verification['status'], 'logon_type': verification['logon_type'],
    'formal_analysis_released': False}))
