from pathlib import Path
import sys
import tkinter as tk
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from spx.desktop import Desktop
from spx.core import ROOT


class DesktopSmokeTests(unittest.TestCase):
    def test_tracking_window_has_41_rows_and_own_data_directory(self):
        window = tk.Tk()
        window.withdraw()
        try:
            app = Desktop(window)
            window.update_idletasks()
            self.assertEqual(window.title(), "SPX Order Tracking")
            self.assertEqual(len(app.table.get_children()), 41)
            self.assertEqual(ROOT, Path(__file__).resolve().parents[1])
            self.assertTrue(callable(app.sheet_settings))
            self.assertTrue(callable(app.tracking_filters))
            self.assertEqual(window.winfo_width(), 68)
            self.assertTrue(window.overrideredirect())
            self.assertTrue(window.attributes("-topmost"))
            self.assertEqual(app.details.state(), "withdrawn")
            app.show_details()
            window.update_idletasks()
            self.assertEqual(app.details.state(), "normal")
        finally:
            window.destroy()
