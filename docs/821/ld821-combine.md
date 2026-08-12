# ld821_combine

Combines all SPL **Time History** files exported from **G4 Utility** into one sorted, analysis-ready CSV for the full deployment. Output uses standardized naming (site, deployment date, system, etc.).

Part of the [821 pipeline](pipeline.md) — run after G4 export is in `RAW/`, before `ld821_to_nvspl.py`.

## Features

- Folder browse for `*Time History*.csv` files (recursive)
- Concatenate + sort by timestamp
- Timestamped log next to output

## Prerequisites

- Python 3.9+, pandas (see `requirements.txt`)

## Inputs

- One or more G4 Time History CSVs under the browsed folder (e.g. `RAW/`)

## Outputs

- **`{site}_Time History.csv`** in the browsed folder
- **`combine_slm_*.log`**

Column headers are **unchanged from G4 export** (passthrough). Expected layout:

| Column | Name |
|--------|------|
| 0 | `Record Type` |
| 1 | `Date` |
| 2 | `LAeq` |
| 3 | `LZeq` |
| 4 | `LCeq` |
| 5 | `External Power` |
| 6–38 | `H12.5` … `H20000` (33 octave bands) |
| 39 | `OVLD` |

See `../../amt2py/schemas/ld821_spl.py` for the full column contract used by `ld821_to_nvspl.py`.

## Usage

1. Run `python ld821_combine.py`
2. Browse to your RAW folder (folder containing G4 Time History CSVs)
3. Enter **Site Name** — used in the output filename (e.g. `DENATRLA_Time History.csv`)
4. Run combine

## NVSPL handoff

Browse the combined file in `ld821_to_nvspl.py` — **Site ID** autofill from the `{site}_Time History.csv` filename; **Output folder** defaults to deployment-level `NVSPL/` when the combined file is in `RAW/`.

## Troubleshooting

- **Invalid timestamps:** check G4 export; `Date` column must be `YYYY-MM-DD HH:MM:SS`
- **NVSPL can't parse output:** confirm first header row contains `Record Type` (no extra preamble lines above the header)
