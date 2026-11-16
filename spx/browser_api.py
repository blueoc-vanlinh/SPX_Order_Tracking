"""Send read-only requests inside the user's authenticated SPX Chrome page."""
from contextlib import contextmanager
import json

from . import core

FETCH = """async ({url, method, params, body, headers}) => {
    const target = new URL(url);
    for (const [key, value] of Object.entries(params || {})) target.searchParams.set(key, String(value));
    if (target.origin !== location.origin || !target.pathname.startsWith('/api/')) throw new Error('Origin mismatch');
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 30000);
    try {
        const csrf = document.cookie.split(';').map(s => s.trim()).find(s => s.startsWith('csrftoken='));
        const sendHeaders = {'Accept': 'application/json, text/plain, */*'};
        if (csrf) sendHeaders['x-csrftoken'] = csrf.substring('csrftoken='.length);
        else if (headers['x-csrftoken']) sendHeaders['x-csrftoken'] = headers['x-csrftoken'];
        if (method === 'POST') sendHeaders['Content-Type'] = 'application/json';
        const response = await window.fetch(target.href, {method, headers: sendHeaders,
            credentials: 'same-origin', redirect: 'manual', signal: controller.signal,
            ...(method === 'POST' ? {body: JSON.stringify(body || {})} : {})});
        return {status: response.type === 'opaqueredirect' ? 302 : response.status,
                headers: {'content-type': response.headers.get('content-type') || ''},
                text: await response.text()};
    } finally { clearTimeout(timer); }
}"""


class Response:
    def __init__(self, value):
        self.status = value['status']
        self.ok = 200 <= self.status < 300
        self.headers = value['headers']
        self.text = value['text']
    def json(self): return json.loads(self.text)
    def dispose(self): pass


class BrowserAPI:
    def __init__(self, page, context):
        self.page, self.context = page, context
    def fetch(self, url, **options):
        return Response(self.page.evaluate(FETCH, {'url': url, 'method': options.get('method', 'GET'),
            'params': options.get('params', {}), 'body': options.get('data', {}),
            'headers': {k: v for k, v in (options.get('headers') or {}).items() if k.lower() == 'x-csrftoken'}}))
    def storage_state(self): return self.context.storage_state()
    def dispose(self): pass


@contextmanager
def session(transport='browser'):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        if transport == 'api':
            api = p.request.new_context(storage_state=str(core.STATE))
            try: yield api
            finally: api.dispose()
            return
        profile = core.AUTH / 'Chrome_OrderTracking'
        existing = (profile / 'Default').exists()
        context = p.chromium.launch_persistent_context(str(profile), channel='chrome', headless=False)
        try:
            if not existing and core.STATE.exists():
                state = json.loads(core.STATE.read_text(encoding='utf-8'))
                context.add_cookies([c for c in state.get('cookies', [])
                                    if c.get('domain', '').lstrip('.') in {'spx.shopee.vn', 'shopee.vn'}])
                # Restore SPX station preferences from the copied session on first run.
                origins = [o for o in state.get('origins', []) if o.get('origin') == core.BASE]
                if origins:
                    context.add_init_script('if (location.origin === ' + json.dumps(core.BASE) + ') { for (const item of ' +
                                            json.dumps(origins[0].get('localStorage', [])) + ') localStorage.setItem(item.name, item.value); }')
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(core.TRACKING_URL, wait_until='domcontentloaded')
            page.wait_for_timeout(1500)
            cookies = context.cookies([core.BASE])
            if not {'spx_uid', 'spx_uk'} <= {c['name'] for c in cookies if c.get('value')}:
                raise core.CrawlError('Chrome chưa có phiên SPX hợp lệ. Bấm ↪ đăng nhập, rồi ✓ lưu phiên.')
            yield BrowserAPI(page, context)
        finally:
            context.close()
