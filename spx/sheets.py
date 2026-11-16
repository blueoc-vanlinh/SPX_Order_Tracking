"""Optional, append-only Google Sheets export of the same spreadsheet cells."""
import json
from pathlib import Path
import re
from urllib.parse import quote

from .core import ROOT, CrawlError, write_json
from .exporting import table

DEFAULTS = {"enabled": False, "spreadsheet_id": "", "worksheet": "Onsite", "credentials_file": ""}


def load_config(filename="google_sheets.json", defaults=None):
    defaults = DEFAULTS if defaults is None else defaults
    path = ROOT / "config" / filename
    return {**defaults, **json.loads(path.read_text(encoding="utf-8-sig"))} if path.exists() else dict(defaults)


def spreadsheet_id(value):
    value = value.strip()
    match = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", value)
    value = match[1] if match else value
    if not re.fullmatch(r"[A-Za-z0-9_-]{10,}", value):
        raise CrawlError("Google Sheets: nhap dung URL hoac ID bang tinh.")
    return value


def authorized_session(cfg):
    from google.auth.transport.requests import AuthorizedSession
    path = Path(cfg.get("credentials_file", ""))
    if not path.is_absolute():
        path = ROOT / path
    try:
        info = json.loads(path.read_text(encoding="utf-8-sig"))
        if info.get("type") == "service_account":
            from google.oauth2.service_account import Credentials
            credentials = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        else:
            from google.oauth2.credentials import Credentials
            credentials = Credentials.from_authorized_user_info(info)
        return AuthorizedSession(credentials, refresh_timeout=30)
    except Exception:
        raise CrawlError("Google Sheets: khong doc duoc JSON Service Account/OAuth da chon.") from None


def upload_station_totals(rows, cfg, session=None, before_write=None, template_only=False):
    """Update only total cells matched to station names in the user's template."""
    owned = session is None
    session = authorized_session(cfg) if owned else session
    base = "https://sheets.googleapis.com/v4/spreadsheets/" + spreadsheet_id(cfg["spreadsheet_id"])
    def request(method, url, **kwargs):
        nonlocal session
        if method != "GET" and before_write is not None:
            before_write()
        try:
            response = session.request(method, url, timeout=45, **kwargs)
            if owned and method == "GET" and url == base and response.status_code in {401, 403} and cfg.get("fallback_credentials_file"):
                session.close()
                session = authorized_session({"credentials_file": cfg["fallback_credentials_file"]})
                response = session.request(method, url, timeout=45, **kwargs)
        except Exception:
            raise CrawlError("Khong ket noi duoc Google Sheets; so lieu da luu o Excel. Kiem tra Sheet truoc khi thu gui lai.") from None
        if not response.ok:
            raise CrawlError(f"Google Sheets HTTP {response.status_code}: kiem tra quyen cua tai khoan da chon.")
        return response.json()
    def normalized(value):
        return " ".join(str(value).strip().casefold().split())
    def column(index):
        result = ""
        while index:
            index, digit = divmod(index - 1, 26)
            result = chr(65 + digit) + result
        return result
    try:
        metadata = request("GET", base, params={"fields": "sheets.properties"})
        title = cfg.get("worksheet", "").strip()
        props = next((s["properties"] for s in metadata.get("sheets", [])
                      if (s["properties"]["title"] == title if title else
                          s["properties"]["sheetId"] == int(cfg.get("worksheet_gid", 0)))), None)
        if props is None:
            if not title:
                raise CrawlError("Khong tim thay tab gid da chon; nhap ten tab trong cau hinh Sheet.")
            created = request("POST", base + ":batchUpdate", json={"requests": [{"addSheet": {"properties": {"title": title}}}]})
            props = created["replies"][0]["addSheet"]["properties"]
        a1 = "'" + props["title"].replace("'", "''") + "'"
        raw = request("GET", base + "/values/" + quote(a1, safe=""), params={"valueRenderOption": "UNFORMATTED_VALUE"}).get("values", [])
        station_header = normalized(cfg.get("station_column", "station"))
        total_header = normalized(cfg.get("total_column", "order total"))
        aliases = {normalized(v): normalized("Hung Yen SOC") for v in ["ALL", "HY SOC", "Hung Yen SOC"]}
        def station_key(value):
            key = normalized(value)
            return aliases.get(key, key)
        updates = []
        insert_header = False
        required_width = max((len(row) for row in raw), default=2)
        incoming_names = {station_key(row['station']) for row in rows}
        if raw:
            headers = [normalized(c) for c in raw[0]]
            if headers.count(station_header) > 1 or headers.count(total_header) > 1:
                raise CrawlError("Sheet có header trùng tên; chưa thể xác định cột ghi an toàn.")
            data_columns = [i for i, cell in enumerate(raw[0]) if station_key(cell) in incoming_names]
            if station_header not in headers and total_header not in headers and len(data_columns) == 1:
                # Existing station data starts on row 1: insert a header, preserving it.
                insert_header = True
                si = data_columns[0]
                ti = si + 1
                if ti < required_width and any(len(row) > ti and row[ti] != '' and
                        (isinstance(row[ti], bool) or not isinstance(row[ti], (int, float))) for row in raw):
                    ti = required_width
                required_width = max(required_width, si + 1, ti + 1)
                header_row = [''] * required_width
                header_row[si], header_row[ti] = cfg.get('station_column', 'station'), cfg.get('total_column', 'order total')
                raw = [header_row] + raw
                updates.append({'range': f'{a1}!A1:{column(required_width)}1', 'values': [header_row]})
            else:
                # Fill missing headers in empty columns; append columns if occupied.
                used = set()
                indices = []
                for label, text in [(station_header, cfg.get('station_column', 'station')),
                                    (total_header, cfg.get('total_column', 'order total'))]:
                    if label in headers:
                        index = headers.index(label)
                    else:
                        index = next((i for i in range(required_width) if i not in used
                                      and (i >= len(headers) or not headers[i])
                                      and all(len(row) <= i or row[i] == '' for row in raw[1:])), required_width)
                        required_width = max(required_width, index + 1)
                        updates.append({'range': f'{a1}!{column(index + 1)}1', 'values': [[text]]})
                    used.add(index)
                    indices.append(index)
                si, ti = indices
        else:
            si, ti = 0, 1
            updates.append({"range": a1 + "!A1:B1", "values": [[cfg.get("station_column", "station"), cfg.get("total_column", "order total")]]})
        positions = {}
        for number, row in enumerate(raw[1:], 2):
            if len(row) > si and str(row[si]).strip():
                key = station_key(row[si])
                if key in positions:
                    raise CrawlError("Sheet co station trung ten; hay sua trung truoc khi gui so lieu.")
                positions[key] = number
        end = max(2, len(raw) + 1)
        seen = set()
        for row in rows:
            name = row["station"]
            key = station_key(name)
            if key in seen or (not template_only and (isinstance(row["order total"], bool) or not isinstance(row["order total"], int) or row["order total"] < 0)):
                raise CrawlError("So lieu station/total bi trung hoac khong hop le.")
            seen.add(key)
            number = positions.get(key)
            if number is None:
                number, end = end, end + 1
                updates.append({"range": f"{a1}!{column(si + 1)}{number}", "values": [[name]]})
            if not template_only:
                updates.append({"range": f"{a1}!{column(ti + 1)}{number}", "values": [[row["order total"]]]})
        if insert_header:
            request('POST', base + ':batchUpdate', json={'requests': [{'insertDimension': {
                'range': {'sheetId': props['sheetId'], 'dimension': 'ROWS', 'startIndex': 0, 'endIndex': 1},
                'inheritFromBefore': False}}]})
        grid = props.get('gridProperties', {})
        capacity = {}
        if end - 1 > grid.get('rowCount', 1000) + int(insert_header):
            capacity['rowCount'] = end - 1
        if required_width > grid.get('columnCount', 26):
            capacity['columnCount'] = required_width
        if capacity:
            request("POST", base + ":batchUpdate", json={"requests": [{"updateSheetProperties": {
                "properties": {"sheetId": props["sheetId"], "gridProperties": capacity},
                "fields": ','.join('gridProperties.' + key for key in capacity)}}]})
        if updates:
            request("POST", base + "/values:batchUpdate", json={"valueInputOption": "RAW", "data": updates})
        if template_only:
            sid = props['sheetId']
            styles = [{"updateSheetProperties": {"properties": {"sheetId": sid,
                       "gridProperties": {"frozenRowCount": max(1, props.get('gridProperties', {}).get('frozenRowCount', 0))}},
                       "fields": "gridProperties.frozenRowCount"}}]
            for index, width in [(si, 350), (ti, 155)]:
                styles.extend([
                    {"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1,
                                   "startColumnIndex": index, "endColumnIndex": index + 1},
                                   "cell": {"userEnteredFormat": {"backgroundColor": {"red": .09, "green": .13, "blue": .18},
                                            "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}}}},
                                   "fields": "userEnteredFormat.backgroundColor,userEnteredFormat.textFormat"}},
                    {"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": index, "endIndex": index + 1},
                                                   "properties": {"pixelSize": width}, "fields": "pixelSize"}}])
            styles.append({"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 1, "startColumnIndex": ti, "endColumnIndex": ti + 1},
                           "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": "#,##0"}}},
                           "fields": "userEnteredFormat.numberFormat"}})
            request("POST", base + ":batchUpdate", json={"requests": styles})
        return len(rows)
    finally:
        if owned:
            session.close()


def ensure_tracking_template(cfg=None, session=None):
    from .tracking import SHEET_DEFAULTS, STATIONS
    cfg = load_config('order_tracking_sheets.json', SHEET_DEFAULTS) if cfg is None else cfg
    rows = [{'station': name, 'order total': None} for name in ['Hung Yen SOC'] + STATIONS]
    return upload_station_totals(rows, cfg, session=session, template_only=True)


def upload(rows, cfg, session=None, before_write=None):
    identifier = spreadsheet_id(cfg["spreadsheet_id"])
    title = cfg.get("worksheet", "Onsite").strip()
    if not title or len(title) > 100 or any(c in title for c in "\r\n"):
        raise CrawlError("Google Sheets: ten tab khong hop le.")
    owned = session is None
    if owned:
        from google.oauth2.service_account import Credentials
        from google.auth.transport.requests import AuthorizedSession
        path = Path(cfg.get("credentials_file", ""))
        if not path.is_absolute():
            path = ROOT / path
        try:
            credentials = Credentials.from_service_account_file(str(path), scopes=["https://www.googleapis.com/auth/spreadsheets"])
        except Exception:
            raise CrawlError("Google Sheets: khong doc duoc tep JSON Service Account.") from None
        session = AuthorizedSession(credentials, refresh_timeout=30)
    base = "https://sheets.googleapis.com/v4/spreadsheets/" + identifier

    def request(method, url, **kwargs):
        if method != "GET" and before_write is not None:
            before_write()
        try:
            response = session.request(method, url, timeout=45, **kwargs)
        except Exception:
            raise CrawlError("Google Sheets: loi ket noi. Excel da duoc luu; kiem tra Sheet truoc khi gui lai de tranh trung du lieu.") from None
        if not response.ok:
            raise CrawlError(f"Google Sheets HTTP {response.status_code}: kiem tra Sheets API, quyen Editor cua Service Account va ID bang tinh. Excel van duoc giu lai.")
        return response.json()

    try:
        columns, values = table(rows)
        if not columns:
            return 0
        metadata = request("GET", base, params={"fields": "sheets.properties"})
        sheet = next((s["properties"] for s in metadata.get("sheets", []) if s["properties"]["title"] == title), None)
        if sheet is None:
            created = request("POST", base + ":batchUpdate", json={"requests": [{"addSheet": {"properties": {
                "title": title, "gridProperties": {"columnCount": max(26, len(columns)), "frozenRowCount": 1}}}}]})
            sheet = created["replies"][0]["addSheet"]["properties"]
        a1 = "'" + title.replace("'", "''") + "'"
        header_url = base + "/values/" + quote(a1 + "!1:1", safe="")
        existing_values = request("GET", header_url).get("values", [])
        existing = [str(v) for v in existing_values[0]] if existing_values else []
        if existing and (len(set(existing)) != len(existing) or any(not v for v in existing)):
            raise CrawlError("Google Sheets: dong tieu de co cot trong/trung. Hay chon tab moi trong cau hinh.")
        headers = list(dict.fromkeys(existing + columns))
        if len(headers) > sheet.get("gridProperties", {}).get("columnCount", 26):
            request("POST", base + ":batchUpdate", json={"requests": [{"updateSheetProperties": {
                "properties": {"sheetId": sheet["sheetId"], "gridProperties": {"columnCount": len(headers)}},
                "fields": "gridProperties.columnCount"}}]})
        if headers != existing:
            request("PUT", base + "/values/" + quote(a1 + "!A1", safe=""),
                    params={"valueInputOption": "RAW"}, json={"values": [headers]})
        index = {name: i for i, name in enumerate(columns)}
        aligned = [[row[index[name]] if name in index else "" for name in headers] for row in values]
        for offset in range(0, len(aligned), 200):
            request("POST", base + "/values/" + quote(a1 + "!A1", safe="") + ":append",
                    params={"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"},
                    json={"majorDimension": "ROWS", "values": aligned[offset:offset + 200]})
        return len(aligned)
    finally:
        if owned:
            session.close()


def publish(run, force=False, config=None, data_file="onsite_view.json"):
    cfg = load_config() if config is None else config
    if not force and not cfg["enabled"]:
        return False
    run = Path(run)
    summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    if not summary.get("complete"):
        raise CrawlError("Google Sheets: chi gui lan cao da hoan tat.")
    marker = run / "google_sheets_status.json"
    if marker.exists():
        state = json.loads(marker.read_text(encoding="utf-8"))
        if state.get("status") == "uploaded":
            print("Lan cao nay da gui Google Sheets; khong gui trung.")
            return True
        raise CrawlError("Lan gui truoc chua ro ket qua. Kiem tra Google Sheets va tep google_sheets_status.json truoc khi gui lai.")
    rows = json.loads((run / data_file).read_text(encoding="utf-8"))
    # A failed or interrupted write may have committed remotely; do not retry it automatically.
    try:
        uploader = upload_station_totals if cfg.get("write_mode") == "station_totals" else upload
        count = uploader(rows, cfg, before_write=lambda: write_json(marker, {"status": "sending", "rows": len(rows)}))
    except Exception:
        if marker.exists():
            write_json(marker, {"status": "check_remote_before_retry", "rows": len(rows)})
        raise
    write_json(marker, {"status": "uploaded", "rows": count})
    print(f"Da gui {count} dong len Google Sheets.")
    return True
