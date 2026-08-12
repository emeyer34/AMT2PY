"""Regression tests for schema header detection (no pandas/tkinter required)."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from amt2py.schemas.feathermc_met import (
    feathermc_met_runtime_indices,
    fuzzy_met_column_indices,
    infer_feathermc_met_gui_indices,
)
from amt2py.schemas.ld821_spl import (
    ld821_csv_header_line_index,
    validate_ld821_header,
)


class SchemaRegressionTests(unittest.TestCase):
    def test_spl_date_time_variant(self):
        hdr = ["Record Type", "Date/Time", "LAeq", "LZeq", "LCeq", "External Power", "H12.5"]
        idx = validate_ld821_header(hdr)
        self.assertEqual(idx["sdate_idx"], 1)
        self.assertEqual(idx["h12p5_idx"], 6)

    def test_feathermc_exact_wind(self):
        hdr = ["#", "Date-Time (UTC)", "Wind Spd Max", "Dir", "Temp", "Date-Time (LOC)", "Time Zone"]
        rt = feathermc_met_runtime_indices(hdr)
        self.assertEqual(rt["spd_idx"], 2)
        self.assertEqual(rt["dir_idx"], 3)

    def test_feathermc_fuzzy_gust_column(self):
        hdr = ["#", "Date-Time (UTC)", "Gust", "Direction", "ADC1", "Date-Time (LOC)", "Time Zone"]
        rt = feathermc_met_runtime_indices(hdr)
        self.assertEqual(rt["spd_idx"], 2)
        self.assertEqual(rt["dir_idx"], 3)
        self.assertEqual(rt["tmp_idx"], 4)

    def test_met_gui_infer_generic(self):
        hdr = ["Date", "Gust m/s", "Wind Dir", "Temperature"]
        fuzzy = fuzzy_met_column_indices(hdr)
        self.assertEqual(fuzzy["spd_idx"], 1)
        self.assertEqual(fuzzy["dir_idx"], 2)
        self.assertEqual(fuzzy["tmp_idx"], 3)

    def test_feathermc_gui_infer_alt_names(self):
        hdr = ["#", "Date-Time (UTC)", "Gust", "Date-Time (LOC)"]
        gui = infer_feathermc_met_gui_indices(hdr)
        self.assertEqual(gui["MET_WINDSPD_IDX"], "2")
        self.assertEqual(gui["MET_TIMESTAMP_IDX"], "3")

    def test_nvspl_output_dir_from_raw(self):
        from amt2py.schemas.ld821_spl import _infer_nvspl_output_dir

        with tempfile.TemporaryDirectory() as root:
            raw = os.path.join(root, "RAW")
            os.makedirs(raw)
            csv_path = os.path.join(raw, "PARK001_Time History.csv")
            open(csv_path, "w").close()
            out = _infer_nvspl_output_dir(csv_path)
            self.assertTrue(out.replace("\\", "/").endswith("/NVSPL") or out.endswith("NVSPL"))
            self.assertEqual(os.path.dirname(out), root)

    def test_nvspl_output_dir_at_deployment_root(self):
        from amt2py.schemas.ld821_spl import _infer_nvspl_output_dir

        with tempfile.TemporaryDirectory() as root:
            csv_path = os.path.join(root, "PARK001_Time History.csv")
            open(csv_path, "w").close()
            out = _infer_nvspl_output_dir(csv_path)
            self.assertEqual(os.path.normpath(out), os.path.normpath(os.path.join(root, "NVSPL")))

    def test_ld821_preamble_skip_index(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write("G4 export metadata\n")
            f.write("Session info\n")
            f.write("Record Type,Date,LAeq,LZeq,LCeq,External Power,H12.5\n")
            path = f.name
        try:
            self.assertEqual(ld821_csv_header_line_index(path), 2)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
