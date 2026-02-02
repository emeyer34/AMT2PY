# Mirrored NSNSD Acoustic Monitoring Toolbox (AMT)

This repository mirrors the **NSNSD Acoustic Monitoring Toolbox (AMT)**, originally a C++ executable for processing, visualizing, and summarizing acoustic data. Due to loss of in-house C++ expertise, this repo adds flexibility by converting core C++ scripts to **Python**, enabling easier maintenance and extension.

---

## Project Overview
- Original AMT: C++ executable for acoustic data workflows.
- This Python port provides equivalent functionality for key tasks:
  - **Merging raw LD831 logger files** into a single `.831` file with proper header and offsets.
  - **Converting `.831` files to NVSPL hourly text format**, with optional external wind data integration.

---

## Included Scripts

### 1. `831Renamer.py`
**Purpose:**
- Recursively discovers folders containing `OverAll`, `SLog`, and `THist` files.
- Merges these into a single `.831` file with `NPSLD831` header and offsets.
- Renames output to `SPL_<SITE>_<yyyy_MM_dd_HHmmss>.831` two levels above the `THist` folder.
- Optional timestamp adjustment for all time-history records.

**Quick Start:**
```bash
python 831Renamer.py /path/to/root --site ABC
# Preview only:
python 831Renamer.py /path/to/root --site ABC --dry-run
# Adjust timestamps:
python 831Renamer.py /path/to/root --site ABC --new-date "2025-04-10 12:34:56"
```

---

### 2. `831_to_NVSPL_external_wind_log.py`
**Purpose:**
- Converts Larson Davis `.831` files (legacy and new formats) to **NVSPL hourly `.txt` files**.
- Optionally merges external wind data from a CSV (MET log) using bin-repeat, forward-fill, or nearest methods.

**Configuration:**
- Edit top-level constants in the script (e.g., `INPUT_PATH`, `OUTPUT_PATH`, `MERGE_MET`, `MET_CSV_PATH`).

**Quick Start:**
```bash
# Basic conversion (no wind merge):
python 831_to_NVSPL_external_wind_log.py

# Enable wind merge:
MERGE_MET = True
MET_CSV_PATH = "path/to/met.csv"
```

---

## Requirements
- Python 3.9+
- Standard library only (optional: `tzdata` for timezone handling).

---

## Why Python?
- Easier maintenance and extension compared to C++.
- Enables integration with modern data science workflows.

---

## Acknowledgments
- Original AMT C++ implementation.
- Larson Davis LD831 data format specifications.
