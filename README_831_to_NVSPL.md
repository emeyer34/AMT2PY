# 831 → NVSPL Converter (with External Wind Merge)

Converts Larson Davis **.831** files (both legacy `LD831` and new `NPSLD831`) into **NVSPL hourly `.txt` files**, and optionally merges **external wind** measurements from a CSV (MET log). The converter parses audio and scalar metrics, aligns timestamps to the **filename anchor**, buckets rows by hour, and writes per‑hour NVSPL outputs.

> Implements robust LD831 parsing (legacy and new formats) and flexible MET merge: encoding/delimiter sniff, tolerant datetime parsing (AM/PM, ISO), and explicit **bin‑repeat** across 1‑second NVSPL records. Includes diagnostics on MET load stats, time ranges, inferred sample interval, and merge counts.

---

## Features

- **LD831 parsing**: Automatically detects `NPSLD831` magic (new) vs. legacy layout and extracts per‑second rows with LAeq/Lceq/Lzeq, voltage, temps, wind, humidity, and octave/third‑octave bands.
- **Filename‑anchored timestamps**: Shifts parsed times so the first row aligns to `SPL_<SITE>_<YYYY_MM_DD_HHMMSS>.831`. (If the stem doesn’t match, it skips anchoring.)
- **External wind merge (optional)**: Loads a CSV (with encoding and delimiter sniff), parses timestamps flexibly, and merges into NVSPL rows via `bin`, `forward`, or `nearest` methods.
- **Diagnostics**: Prints MET load stats (headers/short rows/time fails/wind fails), MET/NVSPL time ranges + overlap, inferred MET sample interval, and merge counts.
- **Hourly output**: Buckets rows by hour and writes `NVSPL_<SITE>_<YYYY_MM_DD_HH>.txt` with the standard NVSPL header.

---

## Requirements

- **Python 3.9+** (uses `zoneinfo` if you enable timezone alignment for MET/LD; otherwise runs with standard library only).
- No external packages required by default. (Optional: `tzdata` on some platforms if you set `LD_TZ` / `MET_TZ`).

---

## Configuration (edit constants at the top of the script)

Open `831_to_NVSPL_external_wind_log.py` and adjust these values:

```python
# Input/Output
INPUT_PATH = r"...\\SPL"         # folder with .831 files or a single .831 file
OUTPUT_PATH = r"...\\NVSPL"      # destination folder for hourly NVSPL .txt
CREATE_SITE_FOLDERS = False     # True to create per-site subfolders under OUTPUT_PATH
RECURSIVE = False               # True to search subfolders for .831 files

# MET (wind) merge
MERGE_MET = False               # set to True to merge external wind
MET_CSV_PATH = r"...\\Met\\met.csv"
MET_TIME_COL = 1                # timestamp column index (0-based)
MET_WIND_COL = 3                # wind column index (e.g., Gust/Max)
MET_DT_FORMAT = None            # None for flexible parsing; or set a concrete strptime format
LD_TZ = None                    # e.g., "America/Denver" if LD timestamps are UTC and you want local
MET_TZ = None                   # e.g., "America/Denver" if MET timestamps include timezone you want adjusted

# Units & conversion
WIND_UNITS = "mps"              # "mps" or "mph"
CONVERT_MPH_TO_MPS = False      # True only if WIND_UNITS == "mph"

# Merge method & interpretation
FILL_METHOD = "bin"             # "bin", "forward", or "nearest"
MET_SAMPLE_STAMP = "end"        # CSV sample timestamps represent "start" | "center" | "end" of bin
BACKFILL_BEFORE_FIRST = False   # bin/backfill seconds before first MET sample if needed
NEAREST_TOLERANCE_SEC = 90      # tolerance window for nearest method
OVERWRITE_EXISTING_WIND = True  # allow replacing any WindSpeed parsed from LD831
```

---

## Quick Start

### 1) Basic conversion (no wind merge)
Edit the constants:

```python
INPUT_PATH = r"C:\\Data\\SPL"
OUTPUT_PATH = r"C:\\Data\\NVSPL"
MERGE_MET = False
CREATE_SITE_FOLDERS = True
RECURSIVE = True
```

Run:

```bash
python 831_to_NVSPL_external_wind_log.py
```

This will parse all `.831` files under `C:\\Data\\SPL` (recursively), anchor timestamps to each filename when possible, bucket rows by hour, and write:  
`NVSPL_<SITE>_<YYYY_MM_DD_HH>.txt` under `C:\\Data\\NVSPL\\<SITE>\\` (because `CREATE_SITE_FOLDERS=True`).

---

### 2) Merge wind using **bin** method (CSV timestamps denote end of bin)

Edit:

```python
MERGE_MET = True
MET_CSV_PATH = r"C:\\Data\\Met\\Station_01.csv"
MET_TIME_COL = 1
MET_WIND_COL = 3        # Gust/Max (or change to Avg column index as needed)
MET_DT_FORMAT = None    # flexible parsing covers AM/PM/ISO/usual patterns
FILL_METHOD = "bin"
MET_SAMPLE_STAMP = "end"  # CSV times are end-of-interval; shift back by inferred interval
BACKFILL_BEFORE_FIRST = False
OVERWRITE_EXISTING_WIND = True
```

Run:

```bash
python 831_to_NVSPL_external_wind_log.py
```

The script prints encoding/delimiter detection, parsed rows, inferred MET interval (e.g., 60 s), first few shifted MET times, and the number of NVSPL rows updated with wind.

---

## Troubleshooting

- **“No .831 files found”** → Check `INPUT_PATH` and `RECURSIVE`. If pointing to a file, ensure the path ends with `.831`.
- **Filename didn’t anchor** → Ensure filenames follow `SPL_<SITE>_<YYYY_MM_DD_HHMMSS>.831`. Otherwise the script skips anchoring.
- **MET parsed 0 rows** → The script prints detection and stats; try a different delimiter, provide `MET_DT_FORMAT`, or share a few lines to tailor parsing.
- **No wind merged** → Check that MET/NVSPL **time ranges overlap**; review diagnostics printed (range and overlap), adjust `MET_SAMPLE_STAMP`, or switch merge method/tolerance.

---

## Output Location & Naming

For each hour with data, the script writes:

```
<OUTPUT_PATH>/<optional_site_subfolder>/NVSPL_<SITE>_<YYYY_MM_DD_HH>.txt
```

If `CREATE_SITE_FOLDERS=True`, a subfolder per site (`<SITE>`) is created; otherwise files are written directly under `OUTPUT_PATH`.

---

## License

Add your preferred license file (e.g., MIT) at the repo root.
