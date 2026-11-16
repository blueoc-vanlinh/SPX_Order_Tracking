import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit, urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from spx import core, google_auth, configuration, sheets


class FakeServer:
    def __init__(self, address, handler):
        self.handler, self.server_port = handler, 54321
        self.query = {}
        self.closed = False
    def handle_request(self):
        response = self.handler.__new__(self.handler)
        response.path = '/?' + urlencode(self.query)
        response.wfile = io.BytesIO()
        response.send_response = lambda status: None
        response.send_header = lambda *args: None
        response.end_headers = lambda: None
        response.do_GET()
    def server_close(self): self.closed = True


class GoogleSetupTests(unittest.TestCase):
    def test_pkce_login_stores_only_own_local_token_and_config(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            servers = []
            def factory(address, handler):
                self.assertEqual(address, ('127.0.0.1', 0))
                server = FakeServer(address, handler)
                servers.append(server)
                return server
            def opener(url):
                query = parse_qs(urlsplit(url).query)
                self.assertEqual(query['code_challenge_method'], ['S256'])
                self.assertEqual(query['scope'], google_auth.SCOPES)
                self.assertEqual(query['prompt'], ['consent select_account'])
                servers[0].query = {'code': 'test-code', 'state': query['state'][0]}
                return True
            exchange = Mock(return_value=Mock(ok=True, json=lambda: {'access_token': 'test-access', 'refresh_token': 'test-refresh', 'expires_in': 3600}))
            with patch.object(core, 'ROOT', root), patch.object(sheets, 'ROOT', root), patch.object(google_auth, 'client_config', return_value={'client_id': 'public-client', 'client_secret': 'desktop-config'}):
                google_auth.connect(opener=opener, exchange=exchange, server_factory=factory)
            token = json.loads((root / google_auth.TOKEN_FILE).read_text())
            self.assertEqual(token['refresh_token'], 'test-refresh')
            self.assertEqual(token['scopes'], google_auth.SCOPES)
            cfg = json.loads((root / 'config/order_tracking_sheets.json').read_text())
            self.assertEqual(cfg['credentials_file'], google_auth.TOKEN_FILE)
            self.assertEqual(cfg['fallback_credentials_file'], '')
            self.assertEqual(exchange.call_args.kwargs['data']['code'], 'test-code')
            self.assertTrue(servers[0].closed)

    def test_google_denial_does_not_create_token(self):
        with tempfile.TemporaryDirectory() as temp:
            root, servers = Path(temp), []
            def factory(address, handler):
                server = FakeServer(address, handler)
                servers.append(server)
                return server
            def opener(url):
                query = parse_qs(urlsplit(url).query)
                servers[0].query = {'error': 'access_denied', 'state': query['state'][0]}
                return True
            exchange = Mock()
            with patch.object(core, 'ROOT', root), patch.object(google_auth, 'client_config', return_value={'client_id': 'client', 'client_secret': 'config'}):
                with self.assertRaises(core.CrawlError):
                    google_auth.connect(opener=opener, exchange=exchange, server_factory=factory)
            exchange.assert_not_called()
            self.assertFalse((root / google_auth.TOKEN_FILE).exists())

    def test_wrong_callback_state_cannot_exchange_code(self):
        with tempfile.TemporaryDirectory() as temp:
            root, servers = Path(temp), []
            def factory(address, handler):
                server = FakeServer(address, handler)
                servers.append(server)
                return server
            def opener(url):
                servers[0].query = {'code': 'stolen', 'state': 'wrong-state'}
                return True
            counter = iter([0, 0, 20])
            exchange = Mock()
            with patch.object(core, 'ROOT', root), patch.object(google_auth, 'client_config', return_value={'client_id': 'client', 'client_secret': 'config'}):
                with self.assertRaises(core.CrawlError):
                    google_auth.connect(opener=opener, exchange=exchange, server_factory=factory, clock=lambda: next(counter), timeout=1)
            exchange.assert_not_called()
            self.assertTrue(servers[0].closed)

    def test_fresh_install_creates_defaults_without_credentials(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(configuration, 'ROOT', root), patch.object(configuration, 'PROGRAM_ROOT', root), patch.object(core, 'ROOT', root), patch.object(core, 'STATE', root / '.auth/storage_state.json'), patch.object(sheets, 'ROOT', root):
                configuration.prepare()
                ready = google_auth.readiness()
                self.assertTrue(ready['sheet'])
                self.assertFalse(ready['google'])
                self.assertFalse(ready['spx'])
                cfg = json.loads((root / 'config/order_tracking.json').read_text())
                self.assertEqual(len(cfg['next_stations']), 40)

    def test_imported_json_is_copied_into_private_data_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'external.json'
            source.write_text(json.dumps({'type': 'service_account', 'client_email': 'bot@example.test', 'private_key': 'test-key'}))
            with patch.object(core, 'ROOT', root / 'app'), patch.object(sheets, 'ROOT', root / 'app'):
                target = google_auth.import_google_file(source)
            self.assertEqual(target, '.auth/google_service_account.json')
            self.assertTrue((root / 'app' / target).exists())
            self.assertTrue(source.exists())

    def test_refreshed_google_token_is_saved_for_next_app_launch(self):
        from google.auth.transport.requests import AuthorizedSession
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            token_path = root / '.auth/google_token.json'
            core.write_json(token_path, {'type': 'authorized_user', 'client_id': 'test-client', 'client_secret': 'public-config',
                                        'token': 'old-access', 'refresh_token': 'test-refresh',
                                        'token_uri': 'https://oauth2.googleapis.com/token', 'scopes': google_auth.SCOPES})
            def refreshed(session, *args, **kwargs):
                session.credentials.token = 'new-access'
                return Mock(ok=True)
            with patch.object(sheets, 'ROOT', root), patch.object(AuthorizedSession, 'request', new=refreshed):
                session = sheets.authorized_session({'credentials_file': '.auth/google_token.json'})
                try: session.request('GET', 'https://sheets.googleapis.com/test')
                finally: session.close()
            saved = json.loads(token_path.read_text())
            self.assertEqual(saved['token'], 'new-access')
            self.assertEqual(saved['refresh_token'], 'test-refresh')

    def test_portable_upgrade_preserves_existing_local_credentials(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            old, new = base / 'portable', base / 'local'
            core.write_json(old / '.auth/token.json', {'token': 'old-portable'})
            core.write_json(new / '.auth/token.json', {'token': 'current-local'})
            with patch.object(configuration, 'ROOT', new), patch.object(configuration, 'PROGRAM_ROOT', old), patch.dict('os.environ', {}, clear=True):
                configuration.prepare()
                self.assertEqual(json.loads((new / '.auth/token.json').read_text()), {'token': 'current-local'})
                self.assertTrue((new / '.portable_import_done').exists())
