"""Create a clean Windows release; only app OAuth configuration may be included."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def build():
    raw = os.environ.get('SPX_GOOGLE_OAUTH_CLIENT_JSON')
    config_file = Path(os.environ.get('SPX_GOOGLE_OAUTH_CLIENT_FILE', str(ROOT / 'assets/google_oauth_client.json')))
    info = json.loads(raw) if raw else json.loads(config_file.read_text(encoding='utf-8-sig'))
    client = info.get('installed', {})
    if not client.get('client_id') or not client.get('client_secret'):
        raise SystemExit('A Google OAuth Desktop client is required for a release with built-in sign-in.')
    if any(key in info for key in ('private_key', 'refresh_token', 'token')):
        raise SystemExit('Account credentials must never be packaged as app configuration.')
    resource = ROOT / 'build/release-resources/google_oauth_client.json'
    resource.parent.mkdir(parents=True, exist_ok=True)
    resource.write_text(json.dumps({'installed': {key: client[key] for key in ('client_id', 'client_secret')}}), encoding='utf-8')
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onedir', '--windowed',
                    '--name', 'SPX_Order_Tracking', '--collect-all', 'playwright',
                    '--add-data', str(resource) + ';assets', '--distpath', str(ROOT / 'release/portable'),
                    '--workpath', str(ROOT / 'build/release-work'), '--specpath', str(ROOT / 'build'),
                    str(ROOT / 'app.pyw')], cwd=ROOT, check=True)
    return package()


def package():
    bundle = ROOT / 'release/portable/SPX_Order_Tracking'
    for name in ('README.md', 'QUICK_SETUP.md'):
        shutil.copy2(ROOT / name, bundle / name)
    files = sorted(p for p in bundle.rglob('*') if p.is_file())
    forbidden = {'service_account.json', 'token.json', 'google_token.json', 'google_service_account.json',
                 'storage_state.json', 'spx_auth_cache.json'}
    for path in files:
        if path.name.lower() in forbidden or '.auth' in path.relative_to(bundle).parts:
            raise SystemExit('Account credential found in release payload.')
        if path.suffix == '.json':
            try: data = json.loads(path.read_text(encoding='utf-8'))
            except (ValueError, UnicodeError): continue
            if isinstance(data, dict) and any(key in data for key in ('private_key', 'refresh_token', 'access_token')):
                raise SystemExit('Account credential found in release JSON.')
    artifact = ROOT / 'release/SPX_Order_Tracking_Windows.zip'
    with zipfile.ZipFile(artifact, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, 'SPX_Order_Tracking/' + path.relative_to(bundle).as_posix())
    print('Clean Windows release:', artifact)


if __name__ == '__main__':
    package() if '--package-only' in sys.argv else build()
