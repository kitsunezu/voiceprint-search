#!/usr/bin/env python3
"""Clean up any leftover smoke test speakers."""
import urllib.request
import json

with urllib.request.urlopen('http://localhost:8000/api/v1/speakers?limit=50') as r:
    data = json.loads(r.read())

speakers = data.get('speakers', [])
total = data.get('total', len(speakers))
smoke = [s for s in speakers if s.get('name', '').startswith('smoke_')]
print(f'Total speakers: {total}')
print(f'Smoke test leftovers: {len(smoke)}')

for s in smoke:
    sid = s['id']
    name = s['name']
    print(f'  Deleting id={sid} name={name}...')
    req = urllib.request.Request(
        f'http://localhost:8000/api/v1/speakers/{sid}',
        method='DELETE'
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
        print('    OK')
    except Exception as e:
        print(f'    ERROR: {e}')

print('Done.')
