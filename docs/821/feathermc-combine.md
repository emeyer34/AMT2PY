# FeatherMC_combine

Combines and cleans wind data from a **Feather MC data logger** (ultrasonic anemometer). Converts UTC → local time with an optional Daylight Saving Time offset, and writes a cleaned MET file named with serial number and deployment date.

Part of the [821 pipeline](pipeline.md) — optional step before `ld821_to_nvspl.py` when merging wind into NVSPL.

## Features

- Select MET folder via GUI (raw logger CSVs auto-detected)
- Skips prior combined outputs and non-logger CSVs
- Time zone picker
- Cleans repeated headers
- UTC to local conversion

## Prerequisites

- Python 3.9+, pandas, pytz (see `requirements.txt`)

## Inputs

- MET folder containing microSD logger CSV exports (`.md` metadata files ignored)
- Only files with `Date-Time (UTC)` and without `Date-Time (LOC)` are combined
- Prior combined outputs (`{serial} {YYYY-MM-DD HHMMSS}.csv`) are skipped

## Outputs

- Combined cleaned CSV written to the selected MET folder (e.g. `00000018 2026-07-09 125259.csv`)
- `feathermc_clean_*.log` in the same folder

## Usage

1. Run `python FeatherMC_combine.py`
2. Browse to the MET folder
3. Enter serial, timezone, and optional DST
4. Run combine

## Configurable settings

Site name (optional log metadata), serial, deploy timezone, adjust for DST.

## Troubleshooting

- **No logger CSVs found** — folder may only contain prior combined outputs; check that raw microSD exports have `Date-Time (UTC)` and not `Date-Time (LOC)`
- **Wrong times in NVSPL** — re-check timezone and DST, then re-run Feather MC combine and NVSPL
