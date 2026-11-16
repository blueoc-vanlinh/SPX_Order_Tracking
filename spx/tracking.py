"""Order Tracking snapshots: one total-only API request per station filter."""
import copy
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from . import core

TRACKING_URL = core.BASE + "/#/orderTracking"
SHEET_ID = "16Gxw2SrgOUULTKRrFJcoQg3Kxzq1z3Iar8Fb7wGDpiM"
STATIONS = [
    "25-HYN Hung Yen 2 Hub", "25-HYN Hung Yen Hub", "25-HYN Kim Dong 2 Hub",
    "25-HYN Kim Dong Hub", "25-HYN Khoai Chau 2 Hub", "25-HYN Khoai Chau 3 Hub",
    "25-HYN Khoai Chau Hub", "25-HYN My Hao 2 Hub", "25-HYN My Hao 3 Hub",
    "25-HYN My Hao Hub", "25-HYN Tan Phuc Hub", "25-HYN Phu Cu Hub",
    "25-HYN Tien Lu Hub", "25-HYN Van Giang 2 Hub", "25-HYN Van Giang 3 Hub",
    "25-HYN An Thi Hub", "25-HYN Van Giang Hub", "25-HYN Van Lam 2 Hub",
    "25-HYN Van Lam 3 Hub", "25-HYN Van Lam 4 Hub", "25-HYN Van Lam Hub",
    "25-HYN Yen My 2 Hub", "25-HYN Yen My 3 Hub", "25-HYN Yen My Hub",
    "BMT SOC", "BN A Mega SOC", "BN B Mega SOC", "Cam Xuyen SOC",
    "Dien Khanh SOC", "Dong Hoi SOC", "Duc Trong SOC", "Gia Nghia SOC",
    "HN SOC", "Kon Tum SOC", "Phan Rang SOC", "Pleiku SOC", "Quang Ngai SOC",
    "Tuy Hoa SOC", "Tuy Phuoc SOC", "Vinh SOC",
]
# Station IDs extracted from SOC/cache/report_station_snapshot.json; responses
# are checked against the requested IDs on every run.
STATION_IDS = [2517, 97, 5980, 612, 2098, 4997, 952, 2400, 5664, 992,
               5098, 1536, 990, 2146, 3951, 982, 985, 1786, 4253, 5266,
               1009, 1538, 4018, 1152, 725, 1701, 1959, 834, 288, 672,
               1041, 1467, 6, 1769, 1579, 1030, 1333, 1791, 324, 549]
SHEET_DEFAULTS = {"enabled": True, "spreadsheet_id": SHEET_ID,
                  "worksheet": "", "worksheet_gid": 0, "credentials_file": ".auth/service_account.json",
                  "fallback_credentials_file": ".auth/token.json", "write_mode": "station_totals",
                  "station_column": "station", "total_column": "order total"}


def defaults():
    return {"path": "/api/fleet_order/order/tracking_list/search", "method": "POST", "request_confirmed": True,
            "params": {}, "body": {"current_station_ids": "3909", "next_station_ids": "",
                                     "order_status": "", "page_no": 1, "count": 24}, "rows_path": "data.list",
            "total_path": "data.total", "success": {"path": "retcode", "equals": 0},
            "pagination": {"mode": "none"}, "delay_seconds": 0.5, "transport": "browser",
            "current_station": {"name": "Hung Yen SOC", "id": 3909},
            "current_filter": {"location": "body", "path": ["current_station_ids"], "value": "3909"},
            "next_filter": {"location": "body", "path": ["next_station_ids"], "all_value": ""},
            "profiles": {"all": {"label": "Tất cả đơn", "filters": {}}}, "active_profile": "all",
            "next_stations": [{"name": name, "value": str(sid)} for name, sid in zip(STATIONS, STATION_IDS)]}


def load_config():
    return json.loads((core.ROOT / "config" / "order_tracking.json").read_text(encoding="utf-8-sig"))


def set_filter(cfg, binding, value):
    """Bindings preserve the exact value type observed in the real request."""
    try:
        location, path = binding["location"], binding["path"]
        if location not in ("params", "body") or not path or not all(isinstance(k, str) for k in path):
            raise ValueError()
        parent = cfg[location]
        for key in path[:-1]:
            parent = parent[key]
        parent[path[-1]] = copy.deepcopy(value)
    except (KeyError, TypeError, ValueError):
        raise core.CrawlError("Order Tracking: lien ket tham so loc chua hop le; can request API thuc te.") from None


def apply_profile(cfg, profile=None):
    result = copy.deepcopy(cfg)
    profile = profile or cfg.get("active_profile", "all")
    profiles = cfg.get("profiles", {"all": {"filters": {}}})
    if profile not in profiles or not isinstance(profiles[profile].get("filters"), dict):
        raise core.CrawlError("Bo loc Order Tracking chua hop le.")
    filters = profiles[profile]["filters"]
    if profile == "all" and filters:
        raise core.CrawlError("Bo all phai de trong de lay tong toan bo HY SOC.")
    reserved = {"current_station_ids", "next_station_ids", "page_no", "count"}
    if reserved.intersection(filters):
        raise core.CrawlError("Bo loc bo sung khong duoc doi Current/Next Station hoac phan trang.")
    result["body"].update(copy.deepcopy(filters))
    result["selected_profile"] = profile
    return result


def requests(cfg):
    if not cfg.get("request_confirmed") or not cfg.get("path"):
        raise core.CrawlError("Order Tracking: chua co API thuc te. Can Request URL, method, query/payload va ID Next Station.")
    core.validate(cfg)
    if cfg.get("pagination", {}).get("mode", "none") != "none":
        raise core.CrawlError("Order Tracking chi doc total, khong phan trang.")
    current, following = cfg.get("current_filter"), cfg.get("next_filter")
    if not current or "value" not in current or current["value"] in (None, "", []):
        raise core.CrawlError("Chua co tham so Current Station Hung Yen SOC tu request that.")
    if cfg.get("current_station", {}).get("id") != 3909:
        raise core.CrawlError("Current Station phai la Hung Yen SOC (3909).")
    if not following or "all_value" not in following:
        raise core.CrawlError("Chua co tham so Next Station va gia tri bo loc rong tu request that.")
    if (current.get("location"), current.get("path")) == (following.get("location"), following.get("path")):
        raise core.CrawlError("Current Station va Next Station khong duoc dung chung tham so.")
    base = copy.deepcopy(cfg)
    set_filter(base, current, current["value"])
    set_filter(base, following, following["all_value"])
    result = [("ALL", base)]
    stations = cfg.get("next_stations", [])
    names, values = set(), set()
    if not stations:
        raise core.CrawlError("Danh sach Next Station dang rong.")
    for station in stations:
        name, value = station.get("name", "").strip(), station.get("value")
        identity = json.dumps(value, sort_keys=True)
        if not name or name == "ALL" or name in names or identity in values or value in (None, "", []):
            raise core.CrawlError("Next Station thieu ID/gia tri loc hoac bi trung; can danh sach tram tu SPX.")
        if value == following["all_value"]:
            raise core.CrawlError("Gia tri Next Station trung bo loc rong.")
        names.add(name)
        values.add(identity)
        request = copy.deepcopy(base)
        set_filter(request, following, value)
        result.append((name, request))
    return result


def read_total(payload, cfg):
    try:
        total = core.at(payload, cfg.get("total_path", "data.total"))
        if isinstance(total, bool) or not isinstance(total, int) or total < 0:
            raise ValueError()
        return total
    except (KeyError, IndexError, TypeError, ValueError):
        raise core.CrawlError("Order Tracking: data.total thieu/khong phai so nguyen khong am; khong thay loi bang 0.") from None


def validate_sample(payload, request):
    """Reject silently ignored station filters before persisting a total."""
    if request["path"] != "/api/fleet_order/order/tracking_list/search":
        return
    data = payload.get("data", {})
    batch = data.get("list")
    if not isinstance(batch, list) or (data.get("total", 0) > 0 and not batch):
        raise core.CrawlError("SPX khong tra mau don de xac minh bo loc; khong ghi total chua kiem tra.")
    expected_next = request["body"].get("next_station_ids", "")
    statuses = str(request["body"].get("order_status", "")).split(",")
    for row in batch:
        if str(row.get("current_station_id")) != "3909":
            raise core.CrawlError("API tra don khac HY SOC; dung de tranh ghi sai total.")
        if expected_next and str(row.get("next_station_id")) != str(expected_next):
            raise core.CrawlError("API khong ap dung dung Next Station; dung de tranh ghi sai total.")
        if statuses != [""] and str(row.get("order_status")) not in statuses:
            raise core.CrawlError("API khong ap dung dung Order Status; dung de tranh ghi sai total.")


def crawl(config=None, stop_event=None, profile=None):
    from .browser_api import session
    cfg = apply_profile(load_config() if config is None else config, profile)
    jobs = requests(cfg)  # Validate every station before making any requests.
    if not core.STATE.exists():
        raise core.CrawlError("Chua co phien SPX. Hay dang nhap truoc.")
    started = datetime.now(timezone(timedelta(hours=7)))
    run = core.ROOT / "outputs" / (started.strftime("%Y%m%d_%H%M%S_%f") + "_order_tracking")
    run.mkdir(parents=True)
    rows, complete = [], False
    try:
        with session(cfg.get('transport', 'browser')) as api:
            try:
                for index, (name, request) in enumerate(jobs):
                    if stop_event is not None and stop_event.is_set():
                        raise core.CrawlError("Da dung Order Tracking; giu so lieu da lay, khong gui Sheet.")
                    cookies = api.storage_state().get("cookies", [])
                    csrf = next((c["value"] for c in cookies if c["name"] == "csrftoken"
                                 and core.urlsplit(core.BASE).hostname.endswith(c["domain"].lstrip("."))), "")
                    payload = core.fetch(api, request, request.get("params", {}), request.get("body", {}),
                                         {"Referer": TRACKING_URL, "Origin": core.BASE,
                                          "Accept": "application/json", "x-csrftoken": csrf})
                    total = read_total(payload, request)
                    validate_sample(payload, request)
                    rows.append({"snapshot_at": started.isoformat(timespec="seconds"),
                                 "observed_at": datetime.now(started.tzinfo).isoformat(timespec="seconds"),
                                 "current_station": "Hung Yen SOC", "current_station_id": 3909,
                                 "next_station": name, "total": total, "filter": cfg["selected_profile"]})
                    # Do not persist data.list, addresses, tracking numbers or raw responses.
                    core.write_json(run / "data.json", rows)
                    print(f"{index + 1}/{len(jobs)} · {name}: {total}")
                    if index + 1 < len(jobs):
                        delay = max(0.0, float(cfg.get("delay_seconds", 0.5)))
                        if stop_event is not None:
                            stop_event.wait(delay)
                        else:
                            time.sleep(delay)
                complete = True
            finally:
                if rows:
                    core.write_json(core.STATE, api.storage_state())
    except core.CrawlError:
        raise
    except Exception as exc:
        raise core.CrawlError("Order Tracking khong chay duoc (" + type(exc).__name__ + "). Kiem tra quyen chay Playwright, ket noi SPX va phien dang nhap; du lieu cu duoc giu lai.") from None
    finally:
        core.write_json(run / "data.json", rows)
        core.export_csv(run / "data.csv", rows)
        from .exporting import export_excel
        export_excel(run / "data.xlsx", rows, title="Order Tracking")
        core.write_json(run / "summary.json", {"kind": "order_tracking", "complete": complete,
                        "rows": len(rows), "expected_rows": len(jobs), "snapshot_at": started.isoformat(),
                        "note": "Sequential live totals; ALL includes destinations outside the selected list."})
        print(f"Da luu so lieu: {run}")
    return run


def publish(run, force=False):
    from . import sheets
    path = Path(run)
    summary = json.loads((path / "summary.json").read_text(encoding="utf-8"))
    if summary.get("kind") != "order_tracking":
        raise core.CrawlError("Day khong phai ket qua Order Tracking.")
    cfg = sheets.load_config("order_tracking_sheets.json", SHEET_DEFAULTS)
    if not summary.get("complete"):
        raise core.CrawlError("Order Tracking chua hoan tat; khong gui so lieu mot phan len Sheet.")
    rows = json.loads((path / "data.json").read_text(encoding="utf-8"))
    output = []
    for row in rows:
        name = "Hung Yen SOC" if row["next_station"] == "ALL" else row["next_station"]
        if row.get("filter", "all") != "all":
            name += " | " + row["filter"]
        output.append({"station": name, "order total": row["total"]})
    core.write_json(path / "sheet_data.json", output)
    return sheets.publish(run, force=force, config=cfg, data_file="sheet_data.json")
