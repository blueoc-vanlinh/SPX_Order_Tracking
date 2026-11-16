"""Google desktop sign-in using PKCE and a loopback callback; no account keys shipped."""
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import secrets
import shutil
import sys
import time
from urllib.parse import urlencode, urlsplit, parse_qs
import webbrowser

import requests
from . import core

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
TOKEN_FILE = '.auth/google_token.json'


def client_config():
    packaged = Path(getattr(sys, '_MEIPASS', core.PROGRAM_ROOT)) / 'assets/google_oauth_client.json'
    local = core.ROOT / '.auth/google_oauth_client.json'
    try:
        config = json.loads((local if local.exists() else packaged).read_text(encoding='utf-8-sig')).get('installed', {})
        if not config.get('client_id') or not config.get('client_secret'):
            raise ValueError()
        return config
    except Exception:
        raise core.CrawlError('Bản app chưa có cấu hình OAuth Desktop. Chọn Nhập cấu hình Google nâng cao hoặc dùng bản EXE phát hành đầy đủ.') from None


def save_account(path):
    from . import sheets, tracking
    cfg = sheets.load_config('order_tracking_sheets.json', tracking.SHEET_DEFAULTS)
    cfg.update(credentials_file=path, fallback_credentials_file='', auth_mode='google', enabled=True)
    core.write_json(core.ROOT / 'config/order_tracking_sheets.json', cfg)


def import_google_file(filename):
    try:
        info = json.loads(Path(filename).read_text(encoding='utf-8-sig'))
        if info.get('type') == 'service_account' and info.get('private_key') and info.get('client_email'):
            target = '.auth/google_service_account.json'
        elif info.get('type') in (None, 'authorized_user') and info.get('refresh_token') and info.get('client_id') and info.get('client_secret'):
            target = TOKEN_FILE
        elif info.get('installed', {}).get('client_id') and info['installed'].get('client_secret'):
            target = '.auth/google_oauth_client.json'
        else:
            raise ValueError()
        core.write_json(core.ROOT / target, info)
        if target != '.auth/google_oauth_client.json':
            save_account(target)
        return target
    except Exception:
        raise core.CrawlError('File cần là Service Account, OAuth token hoặc cấu hình OAuth Desktop hợp lệ.') from None


def connect(stop_event=None, timeout=180, opener=None, exchange=None, clock=None, server_factory=None):
    config = client_config()
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    result = {}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass  # Never log callback URLs/codes.
        def do_GET(self):
            query = parse_qs(urlsplit(self.path).query)
            valid = secrets.compare_digest(query.get('state', [''])[0], state)
            if not valid:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'Invalid sign-in state. Return to the app.')
                return
            if query.get('error'):
                result['error'] = True
            elif query.get('code'):
                result['code'] = query['code'][0]
            else:
                self.send_response(400)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write('<meta charset="utf-8"><h2>Đã nhận phản hồi Google</h2><p>Quay lại SPX Order Tracking để hoàn tất. Bạn có thể đóng tab này.</p>'.encode('utf-8'))
    server = (server_factory or HTTPServer)(('127.0.0.1', 0), Handler)
    server.timeout = .5
    redirect = f'http://127.0.0.1:{server.server_port}/'
    url = 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode({
        'client_id': config['client_id'], 'redirect_uri': redirect, 'response_type': 'code',
        'scope': ' '.join(SCOPES), 'state': state, 'code_challenge': challenge, 'code_challenge_method': 'S256',
        'access_type': 'offline', 'prompt': 'consent select_account'})
    timer = clock or time.monotonic
    try:
        if not (opener or webbrowser.open)(url):
            raise core.CrawlError('Không mở được trình duyệt mặc định để đăng nhập Google.')
        started = timer()
        while not result:
            if stop_event is not None and stop_event.is_set():
                raise core.CrawlError('Đã hủy đăng nhập Google.')
            if timer() - started > timeout:
                raise core.CrawlError('Hết thời gian đăng nhập Google. Bấm Kết nối Google để thử lại.')
            server.handle_request()
    finally:
        server.server_close()
    if result.get('error'):
        raise core.CrawlError('Google chưa cấp quyền. Nếu thấy access_denied, kiểm tra tài khoản được phép trong ứng dụng OAuth hoặc liên hệ quản trị viên Google Workspace.')
    try:
        response = (exchange or requests.post)('https://oauth2.googleapis.com/token', data={
            'client_id': config['client_id'], 'client_secret': config['client_secret'], 'code': result['code'],
            'code_verifier': verifier, 'redirect_uri': redirect, 'grant_type': 'authorization_code'}, timeout=30)
        if not response.ok:
            raise ValueError()
        token = response.json()
        if not token.get('access_token') or not token.get('refresh_token'):
            raise ValueError()
        granted = token.get('scope', '').split()
        if granted and not set(SCOPES) <= set(granted):
            raise core.CrawlError('Google chưa cấp quyền Google Sheets. Đăng nhập lại và cho phép quyền được yêu cầu.')
        info = {'type': 'authorized_user', 'client_id': config['client_id'], 'client_secret': config['client_secret'],
                'token': token['access_token'], 'refresh_token': token['refresh_token'],
                'token_uri': 'https://oauth2.googleapis.com/token', 'scopes': SCOPES}
        from datetime import datetime, timezone, timedelta
        info['expiry'] = (datetime.now(timezone.utc) + timedelta(seconds=int(token.get('expires_in', 3600)))).strftime('%Y-%m-%dT%H:%M:%SZ')
        core.write_json(core.ROOT / TOKEN_FILE, info)
        save_account(TOKEN_FILE)
    except core.CrawlError:
        raise
    except Exception:
        raise core.CrawlError('Không hoàn tất được đăng nhập Google. Kiểm tra mạng, cấu hình OAuth và trạng thái Google Sheets API rồi thử lại.') from None


def readiness():
    from . import sheets, tracking
    cfg = sheets.load_config('order_tracking_sheets.json', tracking.SHEET_DEFAULTS)
    credential = Path(cfg.get('credentials_file') or 'missing')
    if not credential.is_absolute(): credential = core.ROOT / credential
    return {'sheet': bool(cfg.get('spreadsheet_id')), 'google': credential.is_file(), 'spx': core.STATE.is_file()}
