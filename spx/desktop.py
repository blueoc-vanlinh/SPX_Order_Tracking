"""Independent Windows interface for Order Tracking totals."""
import contextlib
import json
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
from pathlib import Path

from .core import ROOT, STATE, CrawlError, login, write_json
from . import tracking


class LogStream:
    def __init__(self, events): self.events = events
    def write(self, value):
        if value: self.events.put(("log", value))
        return len(value)
    def flush(self): pass


class Desktop:
    def __init__(self, window, exit_app=None):
        self.window = window
        self.exit_app = exit_app or window.destroy
        self.events = queue.Queue()
        self.finished = threading.Event()
        self.busy = False
        self.latest = None
        self.setup = None
        self.tooltip = None
        self.drag_origin = None
        self.details = None
        self.log = None
        self.log_lines = []
        self.bg = "#17212e"
        window.title("SPX Order Tracking")
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.attributes("-alpha", 0.62)
        window.configure(bg=self.bg)
        left, top, right, bottom = self.work_area()
        window.geometry(f"68x402+{right - 80}+{max(top, top + (bottom - top - 402) // 2)}")
        frame = tk.Frame(window, bg=self.bg, padx=8, pady=6,
                         highlightbackground="#394657", highlightthickness=1)
        frame.pack(fill="both", expand=True)
        titlebar = tk.Frame(frame, bg=self.bg)
        titlebar.pack(fill="x", pady=(2, 3))
        self.exit_button = tk.Button(titlebar, text="×", command=self.close,
                                     font=("Segoe UI", 13, "bold"), fg="#ff9595",
                                     bg=self.bg, activebackground="#713b45",
                                     activeforeground="white", relief="flat", bd=0,
                                     highlightthickness=0, padx=0, pady=0, cursor="hand2")
        self.exit_button.pack(side="right")
        self.bind_tip(self.exit_button, "Tắt công cụ")
        header = tk.Label(titlebar, text="SPX", font=("Segoe UI", 8, "bold"),
                          fg="#ffb078", bg=self.bg, cursor="fleur")
        header.pack(side="left", fill="x", expand=True)
        header.bind("<ButtonPress-1>", self.drag_start)
        header.bind("<B1-Motion>", self.drag_move)
        header.bind("<ButtonRelease-1>", self.drag_end)
        self.bind_tip(header, "Kéo để di chuyển thanh công cụ")
        self.status = tk.StringVar()
        self.hint = tk.StringVar(value="Bấm ▶ để lấy total HY SOC và 40 Next Station.")
        self.indicator = tk.Label(frame, text="●", fg="#95a1b2", bg=self.bg,
                                  font=("Segoe UI", 8))
        self.indicator.pack()
        self.bind_tip(self.indicator, lambda: self.hint.get() + "\n" + self.status.get())
        self.actions = []
        for icon, tip, mode in [("↪", "Đăng nhập SPX Order Tracking", "login"),
                                ("▶", "Lấy total HY SOC / Next Station và lưu Sheet", "crawl")]:
            button = self.icon_button(frame, icon, tip, lambda m=mode: self.start(m))
            self.actions.append(button)
        self.save = self.icon_button(frame, "✓", "Lưu phiên đăng nhập", self.finish)
        self.save.configure(state="disabled", fg="#72e0af")
        self.icon_button(frame, "■", "Dừng lấy total", self.stop)
        tk.Frame(frame, bg="#394657", height=1).pack(fill="x", pady=5)
        self.icon_button(frame, "▤", "Mở kết quả CSV / JSON", self.open_outputs)
        self.icon_button(frame, "⋯", "Nhật ký và cấu hình", self.show_details)
        window.update_idletasks()
        height = frame.winfo_reqheight()
        window.geometry(f"68x{height}+{right - 80}+{max(top, top + (bottom - top - height) // 2)}")
        window.protocol("WM_DELETE_WINDOW", self.close)
        self.status.set("Order Tracking · " + str(ROOT))
        self.create_details()
        self.details.withdraw()
        window.after(100, self.poll)
        window.after(120, self.update_opacity)

    def work_area(self):
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            rect = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(rect), 0):
                return rect.left, rect.top, rect.right, rect.bottom
        return 0, 0, self.window.winfo_screenwidth(), self.window.winfo_screenheight()

    def icon_button(self, parent, icon, tip, command):
        button = tk.Button(parent, text=icon, command=command, font=("Segoe UI Symbol", 18),
                           bg=self.bg, fg="#edf3fa", activebackground="#35475d",
                           activeforeground="#ffb078", disabledforeground="#536173",
                           relief="flat", bd=0, highlightthickness=0, cursor="hand2",
                           takefocus=True, pady=0)
        button.pack(fill="x", pady=1)
        button.bind("<Enter>", lambda e: button.configure(bg="#29394c"))
        button.bind("<Leave>", lambda e: button.configure(bg=self.bg))
        self.bind_tip(button, tip)
        return button

    def bind_tip(self, widget, tip):
        widget.bind("<Enter>", lambda e: self.show_tip(widget, tip), add="+")
        widget.bind("<Leave>", lambda e: self.hide_tip(), add="+")
        widget.bind("<ButtonPress-1>", lambda e: self.hide_tip(), add="+")

    def show_tip(self, widget, tip):
        self.hide_tip()
        popup = self.tooltip = tk.Toplevel(self.window)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        tk.Label(popup, text=tip() if callable(tip) else tip, bg="#263548", fg="white",
                 font=("Segoe UI", 10), padx=12, pady=8, wraplength=310, justify="left").pack()
        popup.update_idletasks()
        left, top, right, bottom = self.work_area()
        x = max(left, min(right - popup.winfo_reqwidth(), self.window.winfo_x() - popup.winfo_reqwidth() - 8))
        y = max(top, min(bottom - popup.winfo_reqheight(), widget.winfo_rooty()))
        popup.geometry(f"+{x}+{y}")

    def hide_tip(self):
        if self.tooltip is not None:
            self.tooltip.destroy()
            self.tooltip = None

    def update_opacity(self):
        x, y = self.window.winfo_pointerxy()
        inside = (self.window.winfo_x() <= x < self.window.winfo_x() + self.window.winfo_width()
                  and self.window.winfo_y() <= y < self.window.winfo_y() + self.window.winfo_height())
        self.window.attributes("-alpha", 0.96 if inside else 0.62)
        self.window.after(120, self.update_opacity)

    def drag_start(self, event):
        self.drag_origin = (event.x_root - self.window.winfo_x(), event.y_root - self.window.winfo_y())

    def drag_move(self, event):
        if self.drag_origin:
            left, top, right, bottom = self.work_area()
            x = max(left, min(right - 68, event.x_root - self.drag_origin[0]))
            y = max(top, min(bottom - self.window.winfo_height(), event.y_root - self.drag_origin[1]))
            self.window.geometry(f"+{x}+{y}")

    def drag_end(self, event):
        self.drag_origin = None

    def create_details(self):
        panel = self.details = tk.Toplevel(self.window)
        panel.title("Order Tracking · Kết quả và cài đặt")
        panel.geometry("760x620")
        ttk.Label(panel, text="Tổng đơn HY SOC và 40 Next Station", font=("Segoe UI", 13, "bold"), padding=12).pack(anchor="w")
        ttk.Label(panel, textvariable=self.hint, wraplength=720, padding=(12, 0)).pack(fill="x")
        buttons = ttk.Frame(panel, padding=12)
        buttons.pack(fill="x")
        for label, action in [("Thiết lập nhanh…", self.quick_setup), ("Google Sheets…", self.sheet_settings), ("Bộ lọc…", self.tracking_filters),
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

    def open_outputs(self):
        folder = ROOT / "outputs"
        folder.mkdir(exist_ok=True)
        os.startfile(str(folder))

    def start(self, mode):
        if self.busy: return
        if mode in {'crawl', 'publish', 'template'}:
            from .google_auth import readiness
            ready = readiness()
            if not (ready['sheet'] and ready['google']) or (mode == 'crawl' and not ready['spx']):
                self.quick_setup()
                self.hint.set('Hoàn tất thiết lập nhanh rồi bấm ▶ để chạy.')
                return
        self.busy = True
        self.hide_tip()
        self.indicator.configure(fg="#ffb078")
        self.finished.clear()
        for button in self.actions: button.configure(state="disabled")
        self.hint.set("Đang mở Chrome…" if mode == "login" else "Chọn tài khoản và cấp quyền trong trình duyệt…" if mode == 'google_login' else "Đang xử lý…")
        def work():
            try:
                with contextlib.redirect_stdout(LogStream(self.events)), contextlib.redirect_stderr(LogStream(self.events)):
                    if mode == "login":
                        def confirm():
                            self.events.put(("confirm", None))
                            self.finished.wait()
                        login(confirm=confirm)
                    elif mode == 'google_login':
                        from .google_auth import connect
                        connect(stop_event=self.finished)
                        self.events.put(('log', 'Da ket noi tai khoan Google.\n'))
                        from .sheets import ensure_tracking_template
                        ensure_tracking_template()
                        self.events.put(('log', 'Da kiem tra quyen ghi va chuan bi Sheet.\n'))
                    elif mode == "template":
                        from .sheets import ensure_tracking_template
                        count = ensure_tracking_template()
                        self.events.put(("log", f"Da tao mau Sheet cho {count} tram; giu nguyen so lieu da co.\n"))
                    elif mode == "crawl":
                        run = tracking.crawl(stop_event=self.finished)
                        self.events.put(("result", str(run)))
                        if self.finished.is_set():
                            raise CrawlError("Đã dừng trước khi gửi Sheet; Excel đã lưu.")
                        sent = tracking.publish(run)
                        self.events.put(("log", "Đã cập nhật Sheet.\n" if sent else "Đã lưu Excel; tự gửi Sheet đang tắt.\n"))
                    else:
                        runs = [p for p in (ROOT / "outputs").glob("*_order_tracking")
                                if (p / "summary.json").exists() and json.loads((p / "summary.json").read_text(encoding="utf-8")).get("complete")]
                        if not runs: raise CrawlError("Chưa có kết quả hoàn tất để gửi Sheet.")
                        tracking.publish(max(runs, key=lambda p: p.name), force=True)
                self.events.put(("done", "Hoàn tất."))
            except Exception as exc:
                self.events.put(("error", str(exc) if isinstance(exc, CrawlError) else type(exc).__name__ + ": kiểm tra kết nối, phiên SPX và cấu hình Sheet."))
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "log":
                    self.log.configure(state="normal")
                    self.log.insert("end", value)
                    self.log.see("end")
                    self.log.configure(state="disabled")
                elif kind == "confirm":
                    self.save.configure(state="normal")
                    self.hint.set("Đăng nhập Chrome, chọn Hung Yen SOC rồi bấm Lưu phiên.")
                elif kind == "result":
                    self.latest = Path(value)
                    rows = json.loads((self.latest / "data.json").read_text(encoding="utf-8"))
                    self.table.delete(*self.table.get_children())
                    for row in rows:
                        name = "Hung Yen SOC" if row["next_station"] == "ALL" else row["next_station"]
                        self.table.insert("", "end", values=(name, f'{row["total"]:,}'))
                elif kind in {"done", "error"}:
                    self.busy = False
                    self.save.configure(state="disabled")
                    for button in self.actions: button.configure(state="normal")
                    self.hint.set(value)
                    self.indicator.configure(fg="#f18a8a" if kind == "error" else "#72e0af")
                    self.refresh_setup()
                    if kind == "error": messagebox.showerror("Order Tracking", value, parent=self.window)
        except queue.Empty: pass
        self.window.after(100, self.poll)

    def refresh_setup(self):
        if self.setup is not None and self.setup.winfo_exists():
            from .google_auth import readiness
            ready = readiness()
            self.setup_status.set('Google: ' + ('đã có thông tin kết nối' if ready['google'] else 'chưa kết nối') +
                                  '\nSPX: ' + ('đã có phiên; sẽ kiểm tra khi chạy' if ready['spx'] else 'chưa đăng nhập'))

    def quick_setup(self):
        from . import sheets
        from .google_auth import import_google_file
        if self.setup is not None and self.setup.winfo_exists():
            self.setup.deiconify()
            self.setup.lift()
            self.refresh_setup()
            return
        cfg = sheets.load_config('order_tracking_sheets.json', tracking.SHEET_DEFAULTS)
        dialog = self.setup = tk.Toplevel(self.window)
        dialog.title('Thiết lập nhanh · SPX Order Tracking')
        dialog.geometry('620x520')
        dialog.resizable(False, False)
        dialog.attributes('-topmost', True)
        body = ttk.Frame(dialog, padding=18)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='Thiết lập một lần trên máy này', font=('Segoe UI', 14, 'bold')).pack(anchor='w')
        ttk.Label(body, text='Đăng nhập tài khoản của bạn; không cần copy token từ máy khác.', wraplength=580).pack(anchor='w', pady=(5, 14))
        ttk.Label(body, text='1. Link Google Sheet').pack(anchor='w')
        link = tk.StringVar(value=cfg.get('spreadsheet_id', ''))
        ttk.Entry(body, textvariable=link).pack(fill='x', pady=5)
        ttk.Label(body, text='Tên tab (để trống dùng tab gid=0)').pack(anchor='w')
        tab = tk.StringVar(value=cfg.get('worksheet', ''))
        ttk.Entry(body, textvariable=tab).pack(fill='x', pady=5)
        def save():
            try:
                value = sheets.load_config('order_tracking_sheets.json', tracking.SHEET_DEFAULTS)
                value.update(spreadsheet_id=sheets.spreadsheet_id(link.get()), worksheet=tab.get().strip(), enabled=True)
                write_json(ROOT / 'config/order_tracking_sheets.json', value)
                self.refresh_setup()
                return True
            except CrawlError as exc:
                messagebox.showerror('Link Sheet chưa đúng', str(exc), parent=dialog)
                return False
        def google():
            if save(): self.start('google_login')
        def verify():
            if save(): self.start('template')
        def import_file():
            if not save(): return
            filename = filedialog.askopenfilename(parent=dialog, title='Chọn JSON Google (tùy chọn nâng cao)', filetypes=[('JSON', '*.json')])
            if not filename: return
            try:
                target = import_google_file(filename)
                self.refresh_setup()
                self.start('google_login' if target.endswith('google_oauth_client.json') else 'template')
            except CrawlError as exc:
                messagebox.showerror('Không nhập được', str(exc), parent=dialog)
        row = ttk.Frame(body)
        row.pack(fill='x', pady=(12, 5))
        for label, command in [('2. Kết nối Google', google), ('3. Đăng nhập SPX', lambda: self.start('login')),
                               ('Kiểm tra Sheet', verify)]:
            button = ttk.Button(row, text=label, command=command)
            button.pack(side='left', padx=(0, 8))
            self.actions.append(button)
        self.setup_status = tk.StringVar()
        ttk.Label(body, textvariable=self.setup_status, wraplength=570).pack(anchor='w', pady=8)
        ttk.Button(body, text='Nhập JSON Google có sẵn (nâng cao)', command=import_file).pack(anchor='w')
        ttk.Label(body, text='Header và dòng trạm được tạo tự động khi ghi. Mỗi tài khoản cần quyền sửa Sheet.', wraplength=580).pack(anchor='w', pady=8)
        footer = ttk.Frame(body)
        footer.pack(fill='x', side='bottom')
        ttk.Button(footer, text='Lưu thiết lập', command=save).pack(side='left')
        ttk.Button(footer, text='Đóng', command=dialog.withdraw).pack(side='right')
        dialog.protocol('WM_DELETE_WINDOW', dialog.withdraw)
        self.refresh_setup()

    def tracking_filters(self):
        from tkinter import ttk
        from .tracking import load_config, apply_profile, requests
        from .core import write_json
        cfg = load_config()
        profiles = cfg.get("profiles", {"all": {"label": "Tất cả đơn", "filters": {}}})
        dialog = tk.Toplevel(self.window)
        dialog.title("Bộ lọc Order Tracking")
        dialog.geometry("560x370")
        tk.Label(dialog, text="Chọn bộ lọc hoặc nhập tên mới. Bộ all luôn lấy tổng toàn bộ HY SOC.", wraplength=530).pack(padx=12, pady=8)
        selected = tk.StringVar(value=cfg.get("active_profile", "all"))
        combo = ttk.Combobox(dialog, textvariable=selected, values=list(profiles))
        combo.pack(fill="x", padx=12)
        tk.Label(dialog, text="Điều kiện bổ sung (JSON từ payload API; ví dụ Order Status dùng trường order_status):", wraplength=530).pack(padx=12, pady=8)
        editor = scrolledtext.ScrolledText(dialog, height=8, font=("Consolas", 10))
        editor.pack(fill="both", expand=True, padx=12)
        def show(event=None):
            editor.delete("1.0", "end")
            editor.insert("1.0", json.dumps(profiles.get(selected.get(), {}).get("filters", {}), ensure_ascii=False, indent=2))
        combo.bind("<<ComboboxSelected>>", show)
        show()
        tk.Label(dialog, text="Current Station giữ HY SOC; vẫn lấy riêng 40 Next Station.\nBộ lọc khác all có dòng Sheet riêng dạng tên trạm | tên bộ lọc.", justify="left").pack(padx=12, pady=8)
        def save():
            try:
                name = selected.get().strip()
                filters = json.loads(editor.get("1.0", "end"))
                if not name or not isinstance(filters, dict) or (name == "all" and filters):
                    raise CrawlError("Nhập tên bộ lọc và JSON object. Bộ all phải để {} để lấy tổng toàn bộ.")
                profiles[name] = {"label": name, "filters": filters}
                value = {**cfg, "profiles": profiles, "active_profile": name}
                requests(apply_profile(value))
                write_json(ROOT / "config" / "order_tracking.json", value)
                dialog.destroy()
            except (ValueError, CrawlError) as exc:
                messagebox.showerror("Chưa lưu được", str(exc), parent=dialog)
        tk.Button(dialog, text="Lưu và dùng bộ lọc này", command=save).pack(pady=8)

    def sheet_settings(self, tracking=True):
        from .sheets import load_config, spreadsheet_id
        from .core import write_json
        if tracking:
            from .tracking import SHEET_DEFAULTS
            cfg = load_config("order_tracking_sheets.json", SHEET_DEFAULTS)
        else:
            cfg = load_config()
        filename = "order_tracking_sheets.json" if tracking else "google_sheets.json"
        dialog = tk.Toplevel(self.window)
        dialog.title("Google Sheets · " + ("Order Tracking" if tracking else "Onsite"))
        dialog.geometry("550x310")
        dialog.transient(self.window)
        enabled = tk.BooleanVar(value=cfg["enabled"])
        tk.Checkbutton(dialog, text="Tự gửi sau mỗi lần cào hoàn tất", variable=enabled).pack(anchor="w", padx=14, pady=8)
        fields = {}
        for key, label in [("spreadsheet_id", "Link hoặc ID Google Sheets"),
                           ("worksheet", "Tên tab (Tracking: để trống dùng tab gid=0)"), ("credentials_file", "File JSON Service Account / OAuth token")]:
            tk.Label(dialog, text=label).pack(anchor="w", padx=14)
            fields[key] = tk.StringVar(value=cfg[key])
            tk.Entry(dialog, textvariable=fields[key]).pack(fill="x", padx=14, pady=(0, 5))
        def choose():
            path = filedialog.askopenfilename(parent=dialog, title="Chọn JSON Service Account", filetypes=[("JSON", "*.json")])
            if path:
                fields["credentials_file"].set(path)
        tk.Button(dialog, text="Chọn file JSON…", command=choose).pack(anchor="w", padx=14)
        tk.Label(dialog, text=("Cập nhật cột order total theo station; giữ nguyên cột khác.\nCó thể dùng JSON Service Account hoặc token tài khoản Google." if tracking else "Chia sẻ bảng tính với client_email trong file JSON, quyền Editor.\nChỉ thêm dòng; giữ nguyên dữ liệu có sẵn."), justify="left").pack(anchor="w", padx=14, pady=6)
        def save():
            value = {**cfg, **{key: variable.get().strip() for key, variable in fields.items()}}
            value["enabled"] = enabled.get()
            try:
                if value["spreadsheet_id"]:
                    value["spreadsheet_id"] = spreadsheet_id(value["spreadsheet_id"])
                credential = Path(value["credentials_file"])
                if not credential.is_absolute():
                    credential = ROOT / credential
                if value["enabled"] and (not value["spreadsheet_id"] or not credential.is_file()):
                    raise CrawlError("Cần link bảng tính và file JSON để bật tự gửi.")
                write_json(ROOT / "config" / filename, value)
            except (CrawlError, OSError) as exc:
                messagebox.showerror("Chưa lưu được", str(exc), parent=dialog)
                return
            dialog.destroy()
        tk.Button(dialog, text="Lưu cấu hình", command=save).pack(anchor="e", padx=14, pady=4)

    def close(self):
        self.hide_tip()
        self.finished.set()
        self.exit_app()


def main(smoke_output=None):
    from .configuration import prepare
    prepare()
    window = tk.Tk()
    window.withdraw()
    if smoke_output:
        app = Desktop(window)
        window.update_idletasks()
        from .google_auth import readiness, client_config
        ready = readiness()
        has_client = True
        try: client_config()
        except CrawlError: has_client = False
        if not all(ready.values()):
            app.quick_setup()
            app.setup.withdraw()
        write_json(Path(smoke_output), {"title": window.title(), "rows": len(app.table.get_children()),
                                      "root": str(ROOT), "frozen": bool(getattr(__import__("sys"), "frozen", False)),
                                      "toolbar_width": window.winfo_width(), "topmost": bool(window.attributes("-topmost")),
                                      "borderless": bool(window.overrideredirect()), "details_state": app.details.state(),
                                      "setup_required": not all(ready.values()), "google_client_included": has_client,
                                      "setup_window_available": app.setup is not None})
        window.destroy()
        return
    from .processes import own_process_tree, exit_process_tree
    job = own_process_tree()
    app = Desktop(window, exit_app=lambda: exit_process_tree(job))
    window.deiconify()
    from .google_auth import readiness
    if not all(readiness().values()):
        window.after(400, app.quick_setup)
    window.mainloop()
    exit_process_tree(job)
