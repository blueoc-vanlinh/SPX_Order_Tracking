import contextlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from spx import core, browser_api


class BrowserAuthTests(unittest.TestCase):
    def test_fetch_runs_in_browser_without_overriding_browser_origin_or_user_agent(self):
        page, context = Mock(), Mock()
        page.evaluate.return_value = {'status': 200, 'headers': {'content-type': 'application/json'}, 'text': '{"retcode":0}'}
        api = browser_api.BrowserAPI(page, context)
        response = api.fetch(core.BASE + '/api/test', method='POST', data={'current_station_ids': '3909'},
                             headers={'x-csrftoken': 'csrf-test', 'Origin': 'bad', 'User-Agent': 'bad'})
        self.assertEqual(response.json(), {'retcode': 0})
        args = page.evaluate.call_args.args[1]
        self.assertEqual(args['headers'], {'x-csrftoken': 'csrf-test'})
        self.assertEqual(args['body']['current_station_ids'], '3909')
        self.assertIn("credentials: 'same-origin'", page.evaluate.call_args.args[0])

    def test_login_verifies_real_api_before_claiming_success(self):
        page = Mock()
        page.evaluate.return_value = {'status': 200, 'headers': {'content-type': 'application/json'},
            'text': json.dumps({'retcode': 0, 'data': {'total': 123, 'list': [{'current_station_id': 3909}]}})}
        context = Mock()
        context.pages = [page]
        context.cookies.return_value = [{'name': 'spx_uid', 'value': 'uid'}, {'name': 'spx_uk', 'value': 'key'}, {'name': 'csrftoken', 'value': 'csrf'}]
        context.storage_state.return_value = {'cookies': [], 'origins': []}
        @contextlib.contextmanager
        def playwright():
            yield types.SimpleNamespace(chromium=types.SimpleNamespace(launch_persistent_context=lambda *a, **kw: context))
        module = types.ModuleType('playwright.sync_api')
        module.sync_playwright = playwright
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.dict(sys.modules, {'playwright.sync_api': module}), patch.object(core, 'AUTH', root), patch.object(core, 'STATE', root / 'state.json'):
                core.login(confirm=lambda: None)
                cache = json.loads((root / 'spx_auth_cache.json').read_text())
                self.assertTrue(cache['verified_by_api'])
                self.assertTrue((root / 'state.json').exists())
                page.evaluate.return_value['status'] = 403
                with self.assertRaisesRegex(core.CrawlError, 'HTTP 403'):
                    core.login(confirm=lambda: None)
        context.close.assert_called()

    def test_http_403_has_distinct_diagnostic_without_credentials(self):
        api = Mock()
        response = Mock(status=403, headers={})
        api.fetch.return_value = response
        with tempfile.TemporaryDirectory() as temp, patch.object(core, 'AUTH', Path(temp)):
            with self.assertRaisesRegex(core.CrawlError, 'HTTP 403'):
                core.fetch(api, {'path': '/api/test', 'method': 'POST'}, {}, {})
            value = json.loads((Path(temp) / 'last_api_status.json').read_text())
            self.assertEqual(value['http_status'], 403)
            self.assertEqual(set(value), {'http_status', 'path', 'time'})
        response.dispose.assert_called_once()
