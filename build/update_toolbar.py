"""Reuse the read-only Onsite toolbar design in the independent Tracking app."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
reference = (root.parent / "SPX_Onsite_Crawler_v2/SPX_Crawler/spx/desktop.py").read_text(encoding="utf-8")
path = root / "spx/desktop.py"
source = path.read_text(encoding="utf-8")
init = reference[reference.index('    def __init__(self, window, exit_app=None):'):reference.index('    def work_area(self):')]
init = init.replace('        self.mode = None\n        from .onsite import VN\n        self.day = tk.StringVar(value=datetime.now(VN).date().isoformat())', '        self.latest = None')
init = init.replace('SPX Onsite Crawler', 'SPX Order Tracking')
init = init.replace('Đăng nhập hoặc bắt cấu hình Onsite để bắt đầu.', 'Bấm ▶ để lấy total HY SOC và 40 Next Station.')
start, end = init.index('        for icon, tip, mode in '), init.index('            button = self.icon_button', init.index('        for icon, tip, mode in '))
init = init[:start] + '''        for icon, tip, mode in [("↪", "Đăng nhập SPX Order Tracking", "login"),
                                ("▶", "Lấy total HY SOC / Next Station và lưu Sheet", "crawl")]:
''' + init[end:]
init = init.replace('Lưu phiên / Kết thúc bắt cấu hình', 'Lưu phiên đăng nhập')
init = init.replace('        tk.Frame(frame, bg="#394657", height=1)', '        self.icon_button(frame, "■", "Dừng lấy total", self.stop)\n        tk.Frame(frame, bg="#394657", height=1)')
init = init.replace('lambda: self.open_folder("outputs")', 'self.open_outputs')
init = init.replace('        self.refresh()\n', '        self.status.set("Order Tracking · " + str(ROOT))\n        self.create_details()\n        self.details.withdraw()\n')
helpers = reference[reference.index('    def work_area(self):'):reference.index('    def show_details(self):')]
details = '''    def create_details(self):
        panel = self.details = tk.Toplevel(self.window)
        panel.title("Order Tracking · Kết quả và cài đặt")
        panel.geometry("760x620")
        ttk.Label(panel, text="Tổng đơn HY SOC và 40 Next Station", font=("Segoe UI", 13, "bold"), padding=12).pack(anchor="w")
        ttk.Label(panel, textvariable=self.hint, wraplength=720, padding=(12, 0)).pack(fill="x")
        buttons = ttk.Frame(panel, padding=12)
        buttons.pack(fill="x")
        for label, action in [("Google Sheets…", self.sheet_settings), ("Bộ lọc…", self.tracking_filters),
                              ("Gửi kết quả gần nhất", lambda: self.start("publish"))]:
            button = ttk.Button(buttons, text=label, command=action)
            button.pack(side="left", padx=(0, 8))
            self.actions.append(button)
        table = ttk.Frame(panel, padding=(12, 0))
        table.pack(fill="both", expand=True)
        self.table = ttk.Treeview(table, columns=("station", "total"), show="headings")
        self.table.heading("station", text="Station")
        self.table.heading("total", text="Order total")
        self.table.column("station", width=520)
        self.table.column("total", width=140, anchor="e")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        self.table.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        for name in ["Hung Yen SOC"] + tracking.STATIONS:
            self.table.insert("", "end", values=(name, "—"))
        self.log = scrolledtext.ScrolledText(panel, height=7, font=("Consolas", 9), state="disabled")
        self.log.pack(fill="x", padx=12, pady=12)
        panel.protocol("WM_DELETE_WINDOW", panel.withdraw)

    def show_details(self):
        self.details.deiconify()
        self.details.lift()

    def finish(self):
        self.finished.set()
        self.save.configure(state="disabled")
        self.hint.set("Đang lưu phiên đăng nhập…")

    def stop(self):
        if self.busy:
            self.finished.set()
            self.hint.set("Đang dừng; giữ các số đã lấy và không gửi kết quả dở lên Sheet.")

'''
start, end = source.index('    def __init__(self, window, exit_app=None):'), source.index('    def open_outputs(self):')
source = source[:start] + init + helpers + details + source[end:]
source = source.replace('        self.busy = True\n        self.finished.clear()', '        self.busy = True\n        self.hide_tip()\n        self.indicator.configure(fg="#ffb078")\n        self.finished.clear()')
source = source.replace('                    self.hint.set(value)\n                    if kind == "error":', '                    self.hint.set(value)\n                    self.indicator.configure(fg="#f18a8a" if kind == "error" else "#72e0af")\n                    if kind == "error":')
source = source.replace('    def close(self):\n        self.finished.set()', '    def close(self):\n        self.hide_tip()\n        self.finished.set()')
source = source.replace('"frozen": bool(getattr(__import__("sys"), "frozen", False))', '"frozen": bool(getattr(__import__("sys"), "frozen", False)),\n                                      "toolbar_width": window.winfo_width(), "topmost": bool(window.attributes("-topmost")),\n                                      "borderless": bool(window.overrideredirect()), "details_state": app.details.state()')
path.write_text(source, encoding="utf-8")
print("Independent Order Tracking toolbar updated.")
