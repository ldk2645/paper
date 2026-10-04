"""Verify the delivered files; this is not a substitute for raw simulation validation."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / 'publication/package_manifest.json').read_text(encoding='utf-8'))
errors = []
for item in manifest['files']:
    path = root / item['path']
    if not path.is_file():
        errors.append({'path': item['path'], 'reason': 'missing'})
    elif hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
        errors.append({'path': item['path'], 'reason': 'hash mismatch'})
print(json.dumps({'status': 'failed' if errors else 'passed', 'files_checked': len(manifest['files']),
                  'raw_batch_validation': 'not performed; full raw batches are not part of this Git package',
                  'errors': errors}, ensure_ascii=False))
raise SystemExit(bool(errors))
