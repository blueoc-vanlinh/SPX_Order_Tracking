import json
from pathlib import Path
from collections import Counter
import time

root = Path(__file__).resolve().parents[1]
for name in ['storage_state.json', 'spx_auth_cache.json']:
    path = root / '.auth' / name
    value = json.loads(path.read_text(encoding='utf-8'))
    cookies = value.get('cookies', [])
    print(name, 'cookies', len(cookies), 'origins', len(value.get('origins', [])))
    for c in cookies:
        if c['name'] in {'spx_uid', 'spx_uk', 'csrftoken', 'fms_user_id', 'fms_user_skey', 'spx_cid', 'spx_st'}:
            print({'name': c['name'], 'domain': c['domain'], 'path': c['path'], 'has_value': bool(c.get('value')),
                   'expired': c.get('expires', -1) > 0 and c['expires'] < time.time()})
    print('duplicate_names', {k:v for k,v in Counter(c['name'] for c in cookies).items() if v > 1})
    print('auth_cookie_variants', {name: len({c['value'] for c in cookies if c['name'] == name}) for name in ['spx_uid', 'spx_uk', 'csrftoken', 'fms_user_skey']})
    if name == 'storage_state.json':
        print('local_storage_names', [{'origin': o['origin'], 'keys': [v['name'] for v in o.get('localStorage', [])]} for o in value.get('origins', [])])
