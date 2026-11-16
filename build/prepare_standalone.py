from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
original = root.parent / "SPX_Onsite_Crawler_v2" / "SPX_Crawler"
desktop = (original / "spx/desktop.py").read_text(encoding="utf-8")
methods = desktop[desktop.index("    def tracking_filters(self):"):desktop.index("    def refresh(self):")]
methods = methods.replace("def sheet_settings(self, tracking=False):", "def sheet_settings(self, tracking=True):")
target = root / "spx/desktop.py"
value = target.read_text(encoding="utf-8")
value = value.replace("    def close(self):", methods + "    def close(self):")
target.write_text(value, encoding="utf-8")
target = root / "spx/core.py"
value = target.read_text(encoding="utf-8")
value = value[:value.index("\ndef crawl(")]
start, end = value.index("ROOT = ("), value.index('\nBASE = ')
value = value[:start] + 'ROOT = Path(os.environ["SPX_ORDER_TRACKING_DATA_DIR"]).resolve() if os.environ.get("SPX_ORDER_TRACKING_DATA_DIR") else PROGRAM_ROOT' + value[end:]
value = value.replace('ONSITE_URL = BASE + "/#/linehaul/onsite-registration/list"', 'TRACKING_URL = BASE + "/#/orderTracking"')
value = value.replace('url=ONSITE_URL', 'url=TRACKING_URL').replace('ChromeDebug_SOC', 'Chrome_OrderTracking')
value = value.replace('Chay capture-onsite truoc.', 'Kiem tra cau hinh Order Tracking.')
target.write_text(value, encoding="utf-8")
print("Standalone sources prepared:", root)
