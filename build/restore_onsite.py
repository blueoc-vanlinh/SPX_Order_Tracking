"""Undo only the Order Tracking edits made during this conversation."""
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
onsite = (root.parent / "SPX_Onsite_Crawler_v2" / "SPX_Crawler").resolve()
modified = ["app.py", "spx/core.py", "spx/configuration.py", "spx/exporting.py", "spx/sheets.py", "spx/desktop.py", "README.md", "scripts/package_app.py"]
with zipfile.ZipFile(root / "build" / "before_onsite_restore.zip", "w", zipfile.ZIP_DEFLATED) as backup:
    for relative in modified:
        backup.write(onsite / relative, relative)

def transform(relative, action):
    path = onsite / relative
    value = action(path.read_text(encoding="utf-8"))
    path.write_text(value, encoding="utf-8")

transform("spx/core.py", lambda v: v.replace('def login(channel="chrome", confirm=None, url=ONSITE_URL):', 'def login(channel="chrome", confirm=None):').replace('page.goto(url, wait_until="domcontentloaded")', 'page.goto(ONSITE_URL, wait_until="domcontentloaded")'))
transform("spx/exporting.py", lambda v: v.replace('def export_excel(path, rows, title="Onsite"):', 'def export_excel(path, rows):').replace('sheet.title = title', 'sheet.title = "Onsite"'))
def restore_sheets(v):
    start = v.index('def load_config(')
    end = v.index('\ndef spreadsheet_id(', start)
    v = v[:start] + '''def load_config():
    path = ROOT / "config" / "google_sheets.json"
    return {**DEFAULTS, **json.loads(path.read_text(encoding="utf-8-sig"))} if path.exists() else dict(DEFAULTS)

''' + v[end:]
    start, end = v.index('\ndef authorized_session('), v.index('\ndef upload(rows,')
    v = v[:start] + '\n' + v[end:]
    v = v.replace('def publish(run, force=False, config=None, data_file="onsite_view.json"):\n    cfg = load_config() if config is None else config', 'def publish(run, force=False):\n    cfg = load_config()')
    v = v.replace('(run / data_file)', '(run / "onsite_view.json")')
    v = v.replace('        uploader = upload_station_totals if cfg.get("write_mode") == "station_totals" else upload\n        count = uploader(', '        count = upload(')
    return v
transform("spx/sheets.py", restore_sheets)
def restore_config(v):
    v = v.replace('    from .tracking import defaults as tracking_defaults, SHEET_DEFAULTS\n', '')
    v = v.replace('"config/google_sheets.json", "config/order_tracking.json", "config/order_tracking_sheets.json",\n                         ".auth/storage_state.json"', '"config/google_sheets.json", ".auth/storage_state.json"')
    v = v.replace('                "order_tracking.json": tracking_defaults(), "order_tracking_sheets.json": dict(SHEET_DEFAULTS),\n', '')
    return v
transform("spx/configuration.py", restore_config)
def restore_app(v):
    start, end = v.index('    sub.add_parser("login-tracking")'), v.index('    all_onsite = ')
    v = v[:start] + v[end:]
    start, end = v.index('    if args.command == "import-soc":'), v.index('    elif args.command == "login":')
    v = v[:start] + v[end:].replace('    elif args.command == "login":', '    if args.command == "login":', 1)
    return v
transform("app.py", restore_app)
def restore_desktop(v):
    v = v.replace('("▶", "Tải chi tiết tất cả khung giờ", "detail"),\n                                ("Σ", "Order Tracking: tổng đơn HY SOC / Next Station", "tracking")', '("▶", "Tải chi tiết tất cả khung giờ", "detail")')
    start, end = v.index('        tracking_buttons = '), v.index('        panel.protocol("WM_DELETE_WINDOW", panel.withdraw)', v.index('        tracking_buttons = '))
    v = v[:start] + v[end:]
    start, end = v.index('    def tracking_filters(self):'), v.index('    def sheet_settings(', v.index('    def tracking_filters(self):'))
    v = v[:start] + v[end:]
    v = v.replace('def sheet_settings(self, tracking=False):', 'def sheet_settings(self):')
    start, end = v.index('        if tracking:\n'), v.index('        dialog = tk.Toplevel', v.index('        if tracking:\n'))
    v = v[:start] + '        cfg = load_config()\n' + v[end:]
    v = v.replace('dialog.title("Google Sheets · " + ("Order Tracking" if tracking else "Onsite"))', 'dialog.title("Cấu hình Google Sheets")')
    v = v.replace('("worksheet", "Tên tab (Tracking: để trống dùng tab gid=0)"), ("credentials_file", "File JSON Service Account / OAuth token")', '("worksheet", "Tên tab"), ("credentials_file", "File JSON Service Account")')
    lines = v.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if 'tk.Label(dialog, text=("Cập nhật cột order total' in line:
            lines[i] = '        tk.Label(dialog, text="Chia sẻ bảng tính với client_email trong file JSON, quyền Editor.\\nChỉ thêm dòng; giữ nguyên dữ liệu có sẵn.", justify="left").pack(anchor="w", padx=14, pady=6)\n'
    v = ''.join(lines)
    v = v.replace('value = {**cfg, **{key: variable.get().strip() for key, variable in fields.items()}}', 'value = {key: variable.get().strip() for key, variable in fields.items()}')
    v = v.replace('                credential = Path(value["credentials_file"])\n                if not credential.is_absolute():\n                    credential = ROOT / credential\n                if value["enabled"] and (not value["spreadsheet_id"] or not credential.is_file()):', '                if value["enabled"] and (not value["spreadsheet_id"] or not Path(value["credentials_file"]).is_file()):')
    v = v.replace('write_json(ROOT / "config" / filename, value)', 'write_json(ROOT / "config" / "google_sheets.json", value)')
    v = v.replace('mode not in {"sheets", "tracking_sheets"}', 'mode != "sheets"')
    v = v.replace('date.fromisoformat(self.day.get()).isoformat() if not mode.startswith("tracking") else None', 'date.fromisoformat(self.day.get()).isoformat()')
    start, end = v.index('                if mode == "tracking":'), v.index('                    def confirm():', v.index('                if mode == "tracking":'))
    v = v[:start] + '                if mode == "login":\n' + v[end:]
    start, end = v.index('                    if mode == "tracking_login":'), v.index('                elif mode == "capture":', v.index('                    if mode == "tracking_login":'))
    v = v[:start] + '                    login(confirm=confirm)\n' + v[end:]
    return v
transform("spx/desktop.py", restore_desktop)
transform("README.md", lambda v: v[:v.index('\nĐã bổ sung chế độ')] + '\n' + v[v.index('\n## App Windows'):])
transform("scripts/package_app.py", lambda v: v.replace(', "crawl_tracking_totals.bat"', '').replace('    files.append((ROOT / "ORDER_TRACKING.md", "ORDER_TRACKING.md"))\n', ''))

created = ["spx/tracking.py", "spx/soc_import.py", "tests/test_tracking.py", "tests/test_tracking_sheet.py",
           "ORDER_TRACKING.md", "crawl_tracking_totals.bat", "config/order_tracking.json", "config/order_tracking_sheets.json",
           ".auth/service_account.json", ".auth/token.json", ".auth/storage_state.json",
           "build/soc_station_map.json", "build/tracking-tests.log"]
for relative in created:
    path = (onsite / relative).resolve()
    assert path.is_relative_to(onsite)
    if path.is_file(): path.unlink()
for relative in ['spx/__pycache__', 'tests/__pycache__']:
    parent = onsite / relative
    if parent.exists():
        for path in parent.glob('*tracking*.pyc'):
            path.unlink()
        for path in parent.glob('soc_import*.pyc'):
            path.unlink()
for path in (onsite / ".auth",):
    if path.is_dir() and not any(path.iterdir()): path.rmdir()
print("Restored Onsite source; removed only files introduced for Tracking.")
