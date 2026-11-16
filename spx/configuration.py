from .core import ROOT, PROGRAM_ROOT, write_json
from .tracking import defaults, SHEET_DEFAULTS
import json
import shutil
import os


def prepare():
    # Upgrade existing portable installations once; never overwrite local sessions.
    if ROOT != PROGRAM_ROOT and not os.environ.get('SPX_ORDER_TRACKING_DATA_DIR') and not (ROOT / '.portable_import_done').exists():
        for relative in ['config/order_tracking.json', 'config/order_tracking_sheets.json',
                         '.auth/storage_state.json', '.auth/spx_auth_cache.json', '.auth/token.json',
                         '.auth/service_account.json', '.auth/google_token.json', '.auth/google_service_account.json']:
            source, target = PROGRAM_ROOT / relative, ROOT / relative
            if source.is_file() and not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        ROOT.mkdir(parents=True, exist_ok=True)
        (ROOT / '.portable_import_done').write_text('1', encoding='utf-8')
    for name, value in [("order_tracking.json", defaults()), ("order_tracking_sheets.json", SHEET_DEFAULTS)]:
        path = ROOT / "config" / name
        if not path.exists():
            write_json(path, value)
