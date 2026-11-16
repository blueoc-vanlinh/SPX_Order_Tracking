from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from spx import core, tracking, sheets
from spx.exporting import export_excel

rows = [{'station': name, 'order total': None} for name in ['Hung Yen SOC'] + tracking.STATIONS]
core.export_csv(core.ROOT / 'Mau_Order_Tracking.csv', rows)
export_excel(core.ROOT / 'Mau_Order_Tracking.xlsx', rows, title='Order Tracking')
try:
    count = sheets.ensure_tracking_template()
    result = {'ok': True, 'stations': count, 'spreadsheet_id': tracking.SHEET_ID}
except Exception as exc:
    result = {'ok': False, 'error': str(exc) if isinstance(exc, core.CrawlError) else type(exc).__name__}
core.write_json(core.ROOT / 'build' / 'sheet-setup-result.json', result)
print(result)
