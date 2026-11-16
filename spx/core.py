import csv
import hashlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

PROGRAM_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
ROOT = Path(os.environ["SPX_ORDER_TRACKING_DATA_DIR"]).resolve() if os.environ.get("SPX_ORDER_TRACKING_DATA_DIR") else PROGRAM_ROOT
BASE = "https://spx.shopee.vn"
TRACKING_URL = BASE + "/#/orderTracking"
AUTH = ROOT / ".auth"
STATE = AUTH / "storage_state.json"

class CrawlError(Exception):
    pass


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    for attempt in range(4):
        try:
            os.replace(temp, path)
            break
        except PermissionError:
            if attempt == 3:
                raise
            time.sleep(0.05 * (attempt + 1))


def login(channel="chrome", confirm=None, url=TRACKING_URL):
    from playwright.sync_api import sync_playwright
    AUTH.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        options = {"headless": False}
        if channel != "chromium":
            options["channel"] = channel
        context = p.chromium.launch_persistent_context(str(AUTH / "Chrome_OrderTracking"), **options)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(url, wait_until="domcontentloaded")
            if confirm is None:
                input("Dang nhap SPX, chon Hung Yen SOC, sau do quay lai day nhan Enter: ")
            else:
                confirm()
            state = context.storage_state()
            cookies = context.cookies([BASE])
            names = {c["name"] for c in cookies}
            if not {"spx_uid", "spx_uk"} <= names:
                raise CrawlError("Chua thay cookie tai khoan SPX. Hay dang nhap lai.")
            from .browser_api import BrowserAPI
            from .tracking import defaults, read_total, validate_sample
            cfg = defaults()
            payload = fetch(BrowserAPI(page, context), cfg, cfg['params'], cfg['body'])
            total = read_total(payload, cfg)
            validate_sample(payload, cfg)
            write_json(STATE, context.storage_state())
            write_json(AUTH / "spx_auth_cache.json", {
                "saved_at": datetime.now().astimezone().isoformat(),
                "base_url": BASE,
                "csrf_token": next((c["value"] for c in cookies if c["name"] == "csrftoken"), ""),
                "cookies": cookies,
                "verified_by_api": True,
            })
            print(f"Da xac minh API Order Tracking va luu phien. Total HY SOC: {total}")
        finally:
            context.close()


def at(value, path):
    for key in path.split(".") if path else []:
        if isinstance(value, list) and key.isdigit():
            value = value[int(key)]
        else:
            value = value[key]
    return value


def validate(cfg):
    if cfg.get("request_confirmed") is False:
        raise CrawlError("Chua co method/params that. Kiem tra cau hinh Order Tracking.")
    path = cfg.get("path", "")
    if not path.startswith("/api/") or urlsplit(path).netloc or "#" in path or "?" in path:
        raise CrawlError("path phai la /api/...; dat query trong params.")
    method = cfg.get("method", "GET").upper()
    if method not in {"GET", "POST"}:
        raise CrawlError("Chi ho tro GET/POST. POST chi dung cho API tra cuu.")
    paging = cfg.get("pagination", {})
    if paging.get("mode", "none") not in {"none", "page"}:
        raise CrawlError("pagination.mode chi ho tro none/page.")
    if paging.get("location", "params") not in {"params", "body"}:
        raise CrawlError("pagination.location phai la params/body.")
    if method == "GET" and paging.get("location") == "body":
        raise CrawlError("GET khong phan trang trong body.")
    if int(paging.get("size", 100)) < 1 or int(paging.get("max_pages", 100)) < 1:
        raise CrawlError("size/max_pages phai > 0.")
    if "rows_path" not in cfg:
        raise CrawlError("Can cau hinh rows_path theo response API.")


def fetch(api, cfg, params, body, headers=None):
    method = cfg.get("method", "GET").upper()
    # Never retry POST automatically; some endpoints can mutate data.
    attempts = 3 if method == "GET" else 1
    for attempt in range(attempts):
        options = dict(method=method, params=params, timeout=30000, max_redirects=0, headers=headers)
        if method == "POST":
            options["data"] = body
        response = api.fetch(BASE + cfg["path"], **options)
        try:
            status = response.status
            write_json(AUTH / 'last_api_status.json', {'http_status': status, 'path': cfg['path'],
                       'time': datetime.now().astimezone().isoformat()})
            if status == 401:
                raise CrawlError("SPX API HTTP 401: phiên đăng nhập chưa được chấp nhận. Bấm ↪ đăng nhập rồi ✓ để xác minh API.")
            if status == 403:
                raise CrawlError("SPX API HTTP 403: máy chủ từ chối yêu cầu. Kiểm tra trang Order Tracking trong Chrome của tool và quyền tài khoản; không kết luận phiên hết hạn.")
            if 300 <= status < 400:
                raise CrawlError(f"SPX API HTTP {status}: bị chuyển hướng. Mở trang Order Tracking trong Chrome của tool để kiểm tra đăng nhập.")
            if status == 429 or status >= 500:
                if attempt + 1 < attempts:
                    time.sleep(2 ** attempt)
                    continue
            if not response.ok:
                raise CrawlError(f"API tra HTTP {status}; khong ghi noi dung loi vao log.")
            if "json" not in response.headers.get("content-type", "").lower():
                raise CrawlError("API khong tra JSON; kiem tra dang nhap va endpoint.")
            payload = response.json()
            success = cfg.get("success")
            if success and at(payload, success["path"]) != success["equals"]:
                raise CrawlError("API bao loi nghiep vu. Kiem tra success/path va quyen truy cap.")
            return payload
        finally:
            response.dispose()


def export_csv(path, rows):
    from .exporting import flat_row
    flat = [flat_row(row) for row in rows]
    columns = list(dict.fromkeys(k for row in flat for k in row))
    with Path(path).open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in flat:
            # Keep spreadsheet viewers from interpreting untrusted strings as formulas.
            writer.writerow({k: "'" + v if isinstance(v, str) and v.startswith(("=", "+", "-", "@", "\t", "\r")) else v for k, v in row.items()})

