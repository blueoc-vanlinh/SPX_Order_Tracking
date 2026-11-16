import contextlib
import copy
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spx import core, tracking, sheets


def configured():
    cfg = tracking.defaults()
    # Test-only endpoint and parameter names; these do not claim an SPX API.
    cfg.update(path="/api/test/tracking", method="POST", request_confirmed=True,
               body={"filters": {"current": [3909], "next": []}, "page_no": 1, "count": 24},
               current_filter={"location": "body", "path": ["filters", "current"], "value": [3909]},
               next_filter={"location": "body", "path": ["filters", "next"], "all_value": []},
               delay_seconds=0, transport='api')
    for index, station in enumerate(cfg["next_stations"]):
        station["value"] = [10000 + index]
    return cfg


class TrackingTests(unittest.TestCase):
    def test_exact_40_destinations_and_one_all_query(self):
        cfg = configured()
        before = copy.deepcopy(cfg)
        jobs = tracking.requests(cfg)
        self.assertEqual(len(tracking.STATIONS), 40)
        self.assertEqual(len(jobs), 41)
        self.assertEqual(jobs[0][1]["body"]["filters"], {"current": [3909], "next": []})
        for index, (_, request) in enumerate(jobs[1:]):
            self.assertEqual(request["body"]["filters"], {"current": [3909], "next": [10000 + index]})
            self.assertEqual(request["body"]["page_no"], 1)
        self.assertEqual(cfg, before)

    def test_unknown_station_never_becomes_unfiltered_total(self):
        cfg = configured()
        cfg["next_stations"][-1]["value"] = None
        with self.assertRaises(core.CrawlError):
            tracking.requests(cfg)
        cfg = configured()
        cfg["next_stations"][1]["value"] = cfg["next_stations"][0]["value"]
        with self.assertRaises(core.CrawlError):
            tracking.requests(cfg)
        with self.assertRaises(core.CrawlError):
            tracking.requests({**tracking.defaults(), "request_confirmed": False})

    def test_total_is_not_list_length_or_zero_on_failure(self):
        self.assertEqual(tracking.read_total({"data": {"total": 473706, "list": [{}] * 24}}, {}), 473706)
        self.assertEqual(tracking.read_total({"data": {"total": 0}}, {}), 0)
        for value in [None, True, -1, 1.5, "bad"]:
            with self.assertRaises(core.CrawlError):
                tracking.read_total({"data": {"total": value}}, {})
        with self.assertRaises(core.CrawlError):
            tracking.read_total({"data": {}}, {})

    def exercise_crawl(self, fail_at=None):
        calls = []
        api = types.SimpleNamespace(storage_state=lambda: {"cookies": [], "origins": []}, dispose=lambda: None)
        @contextlib.contextmanager
        def playwright():
            yield types.SimpleNamespace(request=types.SimpleNamespace(new_context=lambda **kwargs: api))
        module = types.ModuleType("playwright.sync_api")
        module.sync_playwright = playwright
        def fetch(api, cfg, params, body, headers):
            calls.append(copy.deepcopy(body))
            if len(calls) == fail_at:
                raise core.CrawlError("expired")
            return {"retcode": 0, "data": {"total": 473706 if len(calls) == 1 else 0,
                                           "list": [{"shipment_id": "DO_NOT_PERSIST"}]}}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = root / "state.json"
            state.write_text('{}')
            with patch.dict(sys.modules, {"playwright.sync_api": module}), patch.object(core, "ROOT", root), patch.object(core, "STATE", state), patch.object(core, "fetch", side_effect=fetch):
                if fail_at:
                    with self.assertRaises(core.CrawlError):
                        tracking.crawl(configured())
                    run = next((root / "outputs").iterdir())
                else:
                    run = tracking.crawl(configured())
            summary = json.loads((run / "summary.json").read_text())
            rows = json.loads((run / "data.json").read_text())
            self.assertEqual(summary["complete"], fail_at is None)
            self.assertEqual(len(rows), 41 if fail_at is None else fail_at - 1)
            self.assertEqual(rows[0]["total"], 473706)
            self.assertTrue((run / "data.xlsx").exists())
            self.assertFalse(any("DO_NOT_PERSIST" in p.read_text(encoding="utf-8-sig") for p in run.iterdir() if p.suffix in {".json", ".csv"}))
            if fail_at:
                with patch.object(sheets, "upload") as upload:
                    with self.assertRaises(core.CrawlError):
                        tracking.publish(run)
                    upload.assert_not_called()
        return calls

    def test_crawl_uses_one_request_per_filter_even_when_total_huge(self):
        self.assertEqual(len(self.exercise_crawl()), 41)

    def test_failure_keeps_partial_counts_without_upload(self):
        self.assertEqual(len(self.exercise_crawl(fail_at=3)), 3)

    def test_tracking_sheet_defaults_and_separate_data_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "summary.json").write_text('{"kind":"order_tracking","complete":true}')
            (root / "data.json").write_text('[{"next_station":"ALL","total":123}]')
            with patch.object(sheets, "load_config", return_value=tracking.SHEET_DEFAULTS) as load, patch.object(sheets, 'ensure_tracking_template') as ensure, patch.object(sheets, "publish", return_value=True) as publish:
                self.assertTrue(tracking.publish(root))
                load.assert_called_once_with("order_tracking_sheets.json", tracking.SHEET_DEFAULTS)
                self.assertEqual(publish.call_args.kwargs["data_file"], "sheet_data.json")
                self.assertEqual(publish.call_args.kwargs["config"]["spreadsheet_id"], tracking.SHEET_ID)
                self.assertEqual(json.loads((root / "sheet_data.json").read_text()), [{"station": "Hung Yen SOC", "order total": 123}])
                ensure.assert_not_called()

    def test_real_default_payload_uses_csv_station_ids(self):
        jobs = tracking.requests(tracking.apply_profile(tracking.defaults()))
        self.assertEqual(len(jobs), 41)
        self.assertEqual(jobs[0][1]["body"], {"current_station_ids": "3909", "next_station_ids": "", "order_status": "", "page_no": 1, "count": 24})
        self.assertEqual(jobs[-1][1]["body"]["next_station_ids"], "549")

    def test_profiles_preserve_global_totals_and_station_filters(self):
        cfg = tracking.defaults()
        cfg["profiles"]["received"] = {"filters": {"order_status": "1,2"}}
        active = tracking.apply_profile(cfg, "received")
        self.assertEqual(tracking.requests(active)[-1][1]["body"]["order_status"], "1,2")
        self.assertEqual(cfg["body"]["order_status"], "")
        cfg["profiles"]["bad"] = {"filters": {"current_station_ids": "6"}}
        with self.assertRaises(core.CrawlError):
            tracking.apply_profile(cfg, "bad")
        cfg["profiles"]["all"]["filters"] = {"order_status": "1"}
        with self.assertRaises(core.CrawlError):
            tracking.apply_profile(cfg)

    def test_sample_rejects_ignored_next_station_filter(self):
        cfg = tracking.defaults()
        cfg["body"]["next_station_ids"] = "549"
        tracking.validate_sample({"data": {"total": 100, "list": [{"current_station_id": 3909, "next_station_id": 549}]}}, cfg)
        with self.assertRaises(core.CrawlError):
            tracking.validate_sample({"data": {"total": 100, "list": [{"current_station_id": 3909, "next_station_id": 6}]}}, cfg)


if __name__ == "__main__":
    unittest.main()
