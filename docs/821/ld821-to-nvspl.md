# LD821 to NVSPL (`ld821_to_nvspl.py`)

Converts combined SPL and MET data to hourly **NVSPL** text files (54 columns). Merges one-second SPL with wind data when MET merge is enabled. After creating NVSPL files, load them into **AMT** for final processing, graphing, and analysis.

The script opens a **GUI** — configure fields in the window; there is nothing to edit in the source code before running.

For the full 821 workflow (setup, folder layout, and step order), see [`pipeline.md`](pipeline.md). Environment setup (clone, venv, dependencies) is in [`README.md`](../../README.md) → *Prepare Your Machine*.

## Quick start

```bash
python ld821_to_nvspl.py
```

1. Browse to the combined SPL CSV from `ld821_combine.py` (e.g. `CARE001_Time History.csv`). **Site ID** and **Output folder** autofill from the filename and path (`../../amt2py/schemas/ld821_spl.py`).
2. Choose or confirm the output directory (e.g. a `NVSPL/` folder under the deployment).
3. To merge wind: set **Merge MET Data** to `True`, browse to the cleaned MET CSV from `FeatherMC_combine.py`. Column indices autofill from the header (`../../amt2py/schemas/feathermc_met.py`).
4. Click **Run Conversion Process**. Progress and merge details appear in the log window.

**Output:** one file per hour: `NVSPL_{SITE}_{YYYY_MM_DD_HH}.txt` (3600 one-second rows).

---

## Workflow

```
Combined Time History CSV  ({site}_Time History.csv)
        |
        v
 +-----------------------+
 |  Parse & normalize    |  --> one row per second, band levels
 +-----------------------+
        |
        v
MET CSV (optional)
        |
        v
 +-----------------------+
 |  Timestamp align      |  --> map MET samples to SPL seconds
 +-----------------------+
        |
        v
 +-----------------------+
 |  Merge SPL + MET      |  --> WindSpeed, WindDir, TempOut, ...
 +-----------------------+
        |
        v
 +-----------------------+
 |  Write hourly NVSPL   |
 +-----------------------+
        |
        v
NVSPL_{SITE}_{YYYY_MM_DD_HH}.txt
```

---

## GUI fields

### File paths and site info

| Field | Description |
|-------|-------------|
| **Input SPL CSV** | Combined Time History file from step 2 of the pipeline. |
| **Output Folder** | Directory for hourly `.txt` files. Autofill suggests `NVSPL/` beside `RAW/` when the input CSV is in `RAW/`; otherwise `NVSPL/` beside the CSV. Folder is created on Run if missing. |
| **Site ID** | Monitoring site code (e.g. `CARE001`). Autofill parses the filename prefix before `_Time History`. |

### MET (wind) merge

| Field | Description |
|-------|-------------|
| **Merge MET Data** | `True` to merge wind (and optional direction/temp) into NVSPL rows. |
| **MET Data CSV** | Cleaned Feather MC output from `FeatherMC_combine.py`. Browsing autofill column indices and sets merge to `True`. |
| **Timestamp Col Index** | 0-based column for local timestamp. Autofill: `Date-Time (LOC)`. |
| **Wind Speed Col Index** | Autofill: `Wind Spd Max` or `Gust m/s`. |
| **Wind Dir Col Index** | Optional; autofill when a direction column exists in the header. |
| **Temp Col Index** | Optional external temperature column. |

### Alignment and units

| Field | Typical value | Notes |
|-------|---------------|-------|
| **Sample Stamp** | `start` | Feather MC 10 s samples: stamp at interval start. |
| **Fill Method** | `bin` | Repeats each MET sample across its interval; try `forward` or `nearest` if alignment looks wrong. |
| **Nearest Tolerance (s)** | `2` | Max seconds for `nearest` fill. |
| **Backfill Before First** | `False` | For `bin`/`forward`: fill seconds before the first MET sample? |
| **Wind Speed Units** | `mps` | Units in the MET CSV. |
| **Convert MPH to MPS** | `False` | Set `True` if MET wind speed is in mph. |
| **Invalid Speed Entries** | `39.9` | Comma-separated sentinel values blanked in output (common logger error code). |

Column autofill uses exact header names in `../../amt2py/schemas/feathermc_met.py`. If you use a non-Feather MET file, enter column indices manually.

---

## NVSPL hourly file structure

Each output file has **54 columns**. Header row (from the script):

| Columns | Names |
|---------|--------|
| Site, time | `SiteID`, `STime` |
| 1/3-octave bands (33) | `H12p5` … `H20000` |
| Overall levels | `dbA`, `dbC`, `dbF` |
| Logger / MET | `Voltage`, `WindSpeed`, `WindDir`, `TempIns`, `TempOut`, `Humidity` |
| IDs / metadata | `INVID`, `INSID`, `GChar1`–`GChar3` |
| Adjustments | `AdjustmentsApplied`, `CalibrationAdjustment`, `GPSTimeAdjustment`, `GainAdjustment`, `Status` |

Merged wind fills `WindSpeed`, `WindDir`, and `TempOut` when MET merge is enabled.

---

## Timestamp alignment (MET)

Feather MC wind samples cover fixed intervals (typically 10 s). **Sample stamp** chooses which instant within the interval represents the sample:

```
MET sample interval
|-------Interval--------|
^ start                  ^ center              ^ end
```

- **start** — assign at interval start (default for Feather MC)
- **center** — shift left by half the interval
- **end** — shift left by full interval

**Fill method** then maps MET values onto each one-second SPL row:

- **bin** — repeat the MET value across all seconds in its interval
- **forward** — carry the last value forward until the next sample
- **nearest** — pick the closest MET sample within tolerance

---

## Troubleshooting

- **Blank wind columns:** confirm **Merge MET Data** is `True`, MET path is the *combined* Feather MC CSV, and column indices match the header row.
- **Wind time-shifted:** try **Sample Stamp** `start` vs `center`; for 10 s Feather MC data, `start` + `bin` is the usual choice.
- **Missing SPL hours:** check that Time History timestamps are contiguous in the input CSV.
- **Wrong site in filenames:** re-browse the combined SPL CSV so Site ID autofill runs, or type the site code manually.

---

## Related docs

| Topic | File |
|-------|------|
| End-to-end 821 workflow | [`pipeline.md`](pipeline.md) |
| Combine Time History CSVs | [`ld821-combine.md`](ld821-combine.md) |
| Combine Feather MC wind | [`feathermc-combine.md`](feathermc-combine.md) |
| SPL filename / site autofill | `../../amt2py/schemas/ld821_spl.py` |
| MET column names for autofill | `../../amt2py/schemas/feathermc_met.py` |
