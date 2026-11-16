import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spx import sheets, core, tracking


class Response:
    ok = True
    status_code = 200
    def __init__(self, payload):
        self.payload = payload
    def json(self):
        return self.payload


class Session:
    def __init__(self, values):
        self.values, self.calls = values, []
    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if method == "GET" and "/values/" not in url:
            return Response({"sheets": [{"properties": {"sheetId": 0, "title": "Sheet1", "gridProperties": {"rowCount": 1000}}}]})
        if method == "GET":
            return Response({"values": self.values})
        return Response({})


class StationSheetTests(unittest.TestCase):
    def test_update_existing_station_by_name_and_preserve_other_columns(self):
        session = Session([["station", "order total", "notes"], ["Vinh SOC", 1, "keep"], ["HY SOC", 2, "keep"]])
        rows = [{"station": "Hung Yen SOC", "order total": 473706}, {"station": "Vinh SOC", "order total": 0}]
        self.assertEqual(sheets.upload_station_totals(rows, tracking.SHEET_DEFAULTS, session=session), 2)
        mutation = [call for call in session.calls if call[0] != "GET"]
        self.assertEqual(len(mutation), 1)
        self.assertEqual(mutation[0][2]["json"], {"valueInputOption": "RAW", "data": [
            {"range": "'Sheet1'!B3", "values": [[473706]]}, {"range": "'Sheet1'!B2", "values": [[0]]}]})

    def test_missing_station_added_without_overwriting_existing_rows(self):
        session = Session([["station", "order total"], ["Hung Yen SOC", 5]])
        sheets.upload_station_totals([{"station": "Vinh SOC", "order total": 12}], tracking.SHEET_DEFAULTS, session=session)
        data = session.calls[-1][2]["json"]["data"]
        self.assertEqual(data, [{"range": "'Sheet1'!A3", "values": [["Vinh SOC"]]}, {"range": "'Sheet1'!B3", "values": [[12]]}])

    def test_duplicate_stations_reject_before_writing(self):
        for raw in [[["station", "order total"], ["Hung Yen SOC"], ["HY SOC"]]]:
            session = Session(raw)
            with self.assertRaises(core.CrawlError):
                sheets.upload_station_totals([{"station": "Vinh SOC", "order total": 0}], tracking.SHEET_DEFAULTS, session=session)
            self.assertTrue(all(call[0] == "GET" for call in session.calls))

    def test_missing_headers_created_and_counts_written_in_same_request(self):
        session = Session([['notes', 'owner'], ['keep', 'also keep']])
        sheets.upload_station_totals([{'station': 'Hung Yen SOC', 'order total': 123}], tracking.SHEET_DEFAULTS, session=session)
        values = session.calls[-1][2]['json']['data']
        self.assertEqual(values, [
            {'range': "'Sheet1'!C1", 'values': [['station']]},
            {'range': "'Sheet1'!D1", 'values': [['order total']]},
            {'range': "'Sheet1'!C3", 'values': [['Hung Yen SOC']]},
            {'range': "'Sheet1'!D3", 'values': [[123]]}])

    def test_missing_total_header_added_then_existing_station_updated(self):
        session = Session([['station'], ['Hung Yen SOC']])
        sheets.upload_station_totals([{'station': 'Hung Yen SOC', 'order total': 456}], tracking.SHEET_DEFAULTS, session=session)
        self.assertEqual(session.calls[-1][2]['json']['data'], [
            {'range': "'Sheet1'!B1", 'values': [['order total']]},
            {'range': "'Sheet1'!B2", 'values': [[456]]}])

    def test_data_without_header_kept_below_inserted_header(self):
        session = Session([['Hung Yen SOC', 100], ['Vinh SOC', 5]])
        sheets.upload_station_totals([{'station': 'Hung Yen SOC', 'order total': 200}], tracking.SHEET_DEFAULTS, session=session)
        mutations = [call for call in session.calls if call[0] != 'GET']
        self.assertIn('insertDimension', mutations[0][2]['json']['requests'][0])
        self.assertEqual(mutations[-1][2]['json']['data'], [
            {'range': "'Sheet1'!A1:B1", 'values': [['station', 'order total']]},
            {'range': "'Sheet1'!B2", 'values': [[200]]}])

    def test_empty_tab_receives_two_column_template(self):
        session = Session([])
        sheets.upload_station_totals([{"station": "Hung Yen SOC", "order total": 10}], tracking.SHEET_DEFAULTS, session=session)
        data = session.calls[-1][2]["json"]["data"]
        self.assertEqual(data[0], {"range": "'Sheet1'!A1:B1", "values": [["station", "order total"]]})
        self.assertEqual(data[-1], {"range": "'Sheet1'!B2", "values": [[10]]})

    def test_template_preserves_existing_totals_and_adds_missing_station_names(self):
        session = Session([["station", "order total"], ["HY SOC", 473706], ["Vinh SOC", 123]])
        self.assertEqual(sheets.ensure_tracking_template(tracking.SHEET_DEFAULTS, session=session), 41)
        values = next(call[2]['json']['data'] for call in session.calls if call[1].endswith('/values:batchUpdate'))
        self.assertEqual(len(values), 39)
        self.assertTrue(all(item['range'].startswith("'Sheet1'!A") for item in values))
        self.assertTrue(all(item['values'][0][0] not in {'HY SOC', 'Hung Yen SOC', 'Vinh SOC'} for item in values))

    def test_template_leaves_unknown_totals_blank_instead_of_zero(self):
        session = Session([])
        sheets.ensure_tracking_template(tracking.SHEET_DEFAULTS, session=session)
        values = next(call[2]['json']['data'] for call in session.calls if call[1].endswith('/values:batchUpdate'))
        self.assertEqual(len(values), 42)
        self.assertEqual(values[0]['values'], [['station', 'order total']])
        self.assertTrue(all(item['range'].startswith("'Sheet1'!A") for item in values[1:]))


if __name__ == "__main__":
    unittest.main()
