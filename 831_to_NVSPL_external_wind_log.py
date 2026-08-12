#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""831 -> NVSPL converter. Edit the settings below, then run:
    python 831_to_NVSPL_external_wind_log.py
"""

# --- USER CONFIGURATION (edit these as needed) ---
INPUT_PATH = r"C:\Users\Emeyer\OneDrive - DOI\Desktop\DesktopTemp\NSNSD\Projects\CS_Py\TEST\TIMU\SPL"
OUTPUT_PATH = r"C:\Users\Emeyer\OneDrive - DOI\Desktop\DesktopTemp\NSNSD\Projects\CS_Py\TEST\TIMU\NVSPL"
CREATE_SITE_FOLDERS = False
RECURSIVE = False

MERGE_MET = False
MET_CSV_PATH = r"C:\Users\Emeyer\OneDrive - DOI\Desktop\DesktopTemp\NSNSD\Projects\CS_Py\TEST\CANYCOLO_2025\Met\CANY_COLO_Lathrop.csv"
MET_TIME_COL = 1
MET_WIND_COL = 3
MET_DT_FORMAT = None
LD_TZ = None
MET_TZ = None
WIND_UNITS = "mps"
CONVERT_MPH_TO_MPS = False
FILL_METHOD = "bin"
MET_SAMPLE_STAMP = "end"
BACKFILL_BEFORE_FIRST = False
NEAREST_TOLERANCE_SEC = 90
OVERWRITE_EXISTING_WIND = True
# -----------------------------------------------

_CONFIG_KEYS = (
    "INPUT_PATH",
    "OUTPUT_PATH",
    "CREATE_SITE_FOLDERS",
    "RECURSIVE",
    "MERGE_MET",
    "MET_CSV_PATH",
    "MET_TIME_COL",
    "MET_WIND_COL",
    "MET_DT_FORMAT",
    "LD_TZ",
    "MET_TZ",
    "WIND_UNITS",
    "CONVERT_MPH_TO_MPS",
    "FILL_METHOD",
    "MET_SAMPLE_STAMP",
    "BACKFILL_BEFORE_FIRST",
    "NEAREST_TOLERANCE_SEC",
    "OVERWRITE_EXISTING_WIND",
)


def _apply_config(conv):
    import sys

    cfg = sys.modules[__name__]
    for key in _CONFIG_KEYS:
        setattr(conv, key, getattr(cfg, key))


if __name__ == "__main__":
    from amt2py import ld831_to_nvspl as conv

    _apply_config(conv)
    conv.main()
