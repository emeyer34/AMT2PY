# LD831Renamer (Python CLI)

A Python command-line tool that **discovers logger subfolders**, **merges** `OverAll`, `SLog`, and `THist` into a single `.831` file (with the `NPSLD831` header + offsets), and **renames** the output to `SPL_<SITE>_<yyyy_MM_dd_HHmmss>.831` **two levels above** the `THist` folder. Optionally, it can **adjust internal timestamps** in all time‑history records to align with a new date.

This is a Python port of the original WinForms C# utility (`LD831Renamer.cs` + `.designer.cs`) and mirrors its core behavior.

## AMT2PY
Repository for mirrored NSNSD Acoustic Monitoring Toolbox (AMT), a C++ executable for processing, visualizing, and summarizing acoustic data. This repo adds flexibility by converting C++ scripts to Python due to loss of in-house C++ expertise.

---

## Features

- 🔎 **Recursive discovery** of any folder under a given root that contains the trio: `OverAll`, `SLog`, and `THist`.
- 🧬 **Merge** the three data blocks into one `.831` file with a correct `NPSLD831` header and block offsets.
- 🏷️ **Auto-rename** to `SPL_<SITE>_<timestamp>.831` in the **grandparent directory** of `THist`.
- ⏱️ **Optional timestamp adjustment**: shift per-record timestamps by a computed offset based on a user-specified new date.
- 🧪 **Dry-run mode**: preview planned actions without writing or moving files.

---

## Installation

This tool uses **only Python’s standard library**—no external dependencies.

## Quick Start

> `python 831Renamer.py /path/to/root --site ABC`

Use --dry-run to preview without writing:
> `python 831Renamer.py /path/to/root --site ABC --dry-run`

## Usage
Options:

ROOT — Root folder containing subfolders with OverAll, SLog, THist.
--site SITE — Required alphanumeric site ID (uppercased).
--new-date — Optional new date for timestamp adjustment.
--dry-run — Preview actions only.

## Examples

### Basic run
> `python 831Renamer.py ~/data/ld_runs --site SPL1`

### Preview only
> `python 831Renamer.py ~/data/ld_runs --site SPL1 --dry-run`

### Adjust timestamps
> `python 831Renamer.py ~/data/ld_runs --site SPL1 --new-date "2025-04-10 12:34:56"`

## Input/Output
<some-subfolder>/
├─ OverAll
├─ SLog
└─ THist

Output:
SPL_<SITE>_<yyyy_MM_dd_HHmmss>.831 two levels above THist.

# Acknowledgments
Original WinForms C# utility (LD831Renamer.cs) that inspired this Python port.

### Public domain

This project is in the worldwide [public domain](LICENSE.md):

> This project is in the public domain within the United States,
> and copyright and related rights in the work worldwide are waived through the
> [CC0 1.0 Universal public domain dedication](https://creativecommons.org/publicdomain/zero/1.0/).
>
> All contributions to this project will be released under the CC0 dedication.
> By submitting a pull request, you are agreeing to comply with this waiver of copyright interest.
