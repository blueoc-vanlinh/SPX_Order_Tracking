"""Standalone Order Tracking application and packaged startup check."""
import sys
from spx.desktop import main

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == '--setup-sheet':
        from spx import core, sheets
        try:
            count = sheets.ensure_tracking_template()
            core.write_json(sys.argv[2], {'ok': True, 'stations': count})
        except Exception as exc:
            core.write_json(sys.argv[2], {'ok': False, 'error': str(exc) if isinstance(exc, core.CrawlError) else type(exc).__name__})
    elif len(sys.argv) == 3 and sys.argv[1] == '--verify-session':
        from spx import core, tracking
        from spx.browser_api import session
        try:
            cfg = tracking.defaults()
            with session() as api:
                payload = core.fetch(api, cfg, cfg['params'], cfg['body'])
                tracking.validate_sample(payload, cfg)
                total = tracking.read_total(payload, cfg)
                core.write_json(core.STATE, api.storage_state())
            core.write_json(sys.argv[2], {'ok': True, 'total': total, 'transport': 'browser'})
        except Exception as exc:
            core.write_json(sys.argv[2], {'ok': False, 'error': str(exc) if isinstance(exc, core.CrawlError) else type(exc).__name__})
    else:
        main(smoke_output=sys.argv[2] if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test" else None)
