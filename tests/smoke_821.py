#!/usr/bin/env python3
"""
Smoke tests for LD821 processing (parse, hourly split, MET merge, combine).

Run from repo root:
    python tests/smoke_821.py
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
import types
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _install_import_stubs():
    if "tkinter" in sys.modules:
        return

    class _Tk:
        pass

    class _Mixin:
        pass

    tk = types.ModuleType("tkinter")
    for name in ("END", "BOTH", "X", "WORD", "LEFT", "SOLID"):
        setattr(tk, name, name)
    tk.Tk = _Tk
    tk.StringVar = object
    tk.Text = object
    tk.Label = object
    tk.Listbox = object

    ttk = types.ModuleType("tkinter.ttk")
    for name in (
        "Frame", "LabelFrame", "Label", "Entry", "Combobox",
        "Button", "Progressbar", "Scrollbar",
    ):
        setattr(ttk, name, object)

    filedialog = types.ModuleType("tkinter.filedialog")
    filedialog.askopenfilename = lambda **_: ""
    filedialog.askdirectory = lambda **_: ""

    messagebox = types.ModuleType("tkinter.messagebox")
    for name in ("showerror", "showinfo", "showwarning"):
        setattr(messagebox, name, lambda *a, **k: None)
    messagebox.askyesno = lambda *a, **k: True

    tk.ttk = ttk
    tk.filedialog = filedialog
    tk.messagebox = messagebox

    sgc = types.ModuleType("amt2py.shared_gui_components")
    sgc.ToolTip = type("ToolTip", (), {})
    sgc.WorkerGuiMixin = _Mixin
    sgc.add_progress_bar = lambda *a, **k: None
    sgc.add_scrolled_text = lambda *a, **k: object()
    sgc.create_file_logger = lambda *a, **k: (logging.getLogger("smoke"), "smoke.log")
    sgc.close_logger = lambda *a, **k: None
    sgc.pack_combine_layout = lambda parent, owner: parent

    sys.modules.update({
        "tkinter": tk,
        "tkinter.ttk": ttk,
        "tkinter.filedialog": filedialog,
        "tkinter.messagebox": messagebox,
        "amt2py.shared_gui_components": sgc,
    })


_install_import_stubs()

from tests.fixtures import write_combine_parts, write_met_csv, write_spl_csv
import amt2py.ld821_combine as ld821_combine
import amt2py.ld821_to_nvspl as nvspl

SITE = "PARK001"
SPL_SECONDS = 7200  # 2 hours of 1 Hz data
MET_CONFIG = {
    "MERGE_MET": True,
    "MET_TIMESTAMP_IDX": 5,
    "MET_WINDSPD_IDX": 3,
    "MET_WINDDIR_IDX": None,
    "MET_EXTERNTEMP_IDX": None,
    "MET_SAMPLE_STAMP": "start",
    "FILL_METHOD": "bin",
    "NEAREST_TOLERANCE_SEC": 2,
    "BACKFILL_BEFORE_FIRST": False,
    "MET_SPEED_UNITS": "mps",
    "CONVERT_MPH_TO_MPS": False,
    "MET_INVALID_SPEED": {"39.9"},
}


class Smoke821Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls.tmp = cls._tmpdir.name
        cls.spl_path = os.path.join(cls.tmp, "spl.csv")
        cls.met_path = os.path.join(cls.tmp, "met.csv")
        write_spl_csv(cls.spl_path, seconds=SPL_SECONDS)
        write_met_csv(cls.met_path, seconds=SPL_SECONDS)

    @classmethod
    def tearDownClass(cls):
        cls._tmpdir.cleanup()

    def test_parse_spl_row_count(self):
        per_day = nvspl.parse_ld821_to_day_records(SITE, self.spl_path)
        self.assertEqual(sum(len(v) for v in per_day.values()), SPL_SECONDS)

    def test_parse_stores_datetime(self):
        per_day = nvspl.parse_ld821_to_day_records(SITE, self.spl_path)
        rec = next(iter(per_day.values()))[0]
        self.assertIsInstance(rec[1], datetime)

    def test_hourly_split(self):
        per_day = nvspl.parse_ld821_to_day_records(SITE, self.spl_path)
        bundles = nvspl.parse_daily_file_to_hours(SITE, next(iter(per_day.values())))
        self.assertEqual(len(bundles), 2)
        for b in bundles:
            self.assertEqual(len(b["rows"]), 3600)

    def test_nvspl_row_width(self):
        per_day = nvspl.parse_ld821_to_day_records(SITE, self.spl_path)
        rec = next(iter(per_day.values()))[0]
        self.assertEqual(len(rec), len(nvspl.NVSPL_HEADER))

    def test_met_merge_fills_wind(self):
        config = {
            **MET_CONFIG,
            "MET_CSV_PATH": self.met_path,
        }
        per_day = nvspl.parse_ld821_to_day_records(SITE, self.spl_path)
        bundles = nvspl.parse_daily_file_to_hours(SITE, next(iter(per_day.values())))
        samples = nvspl.load_met_samples(config, lambda _m: None)
        self.assertTrue(samples)
        bundles = nvspl.merge_met_for_day(bundles, config, lambda _m: None, met_samples=samples)

        filled = sum(1 for b in bundles for row in b["rows"] if row[39])
        self.assertGreater(filled, 0)

    def test_combine_two_files(self):
        parts_dir = os.path.join(self.tmp, "combine")
        files = write_combine_parts(parts_dir, num_files=2, rows_per_file=100)
        logger = logging.getLogger("smoke_combine")
        logger.handlers.clear()
        logger.addHandler(logging.NullHandler())

        out = ld821_combine.process_slm_files(files, SITE, logger, self.tmp)
        self.assertTrue(os.path.isfile(out))

        import pandas as pd

        df = pd.read_csv(out)
        self.assertEqual(len(df), 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
