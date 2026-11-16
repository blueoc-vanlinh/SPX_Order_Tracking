from .core import ROOT, write_json
from .tracking import defaults, SHEET_DEFAULTS


def prepare():
    for name, value in [("order_tracking.json", defaults()), ("order_tracking_sheets.json", SHEET_DEFAULTS)]:
        path = ROOT / "config" / name
        if not path.exists():
            write_json(path, value)
