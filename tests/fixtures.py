"""Synthetic LD821 Time History and MET CSV fixtures for smoke tests."""

from __future__ import annotations

import argparse
import csv
import os
from datetime import datetime, timedelta

BAND_COLS = [
    "H12.5", "H15.8", "H20", "H25", "H31.5", "H40", "H50", "H63", "H80", "H100",
    "H125", "H160", "H200", "H250", "H315", "H400", "H500", "H630", "H800", "H1000",
    "H1250", "H1600", "H2000", "H2500", "H3150", "H4000", "H5000", "H6300", "H8000",
    "H10000", "H12500", "H16000", "H20000",
]

SPL_HEADER = (
    ["Record Type", "Date", "LAeq", "LZeq", "LCeq", "External Power"]
    + BAND_COLS
    + ["OVLD"]
)


def write_spl_csv(path: str, days: int = 1, *, seconds: int | None = None, start: datetime | None = None) -> int:
    start = start or datetime(2026, 6, 1, 0, 0, 0)
    total_rows = seconds if seconds is not None else days * 86400
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(SPL_HEADER)
        ts = start
        for i in range(total_rows):
            bands = [f"{45.0 + (i % 20) * 0.1:.1f}" for _ in BAND_COLS]
            w.writerow(
                ["SPL", ts.strftime("%Y-%m-%d %H:%M:%S"), "52.3", "54.1", "53.0", "12.4"]
                + bands
                + [""]
            )
            ts += timedelta(seconds=1)
    return total_rows


def write_met_csv(
    path: str,
    days: int = 1,
    *,
    seconds: int | None = None,
    interval_sec: int = 10,
    start: datetime | None = None,
) -> int:
    start = start or datetime(2026, 6, 1, 0, 0, 0)
    total_seconds = seconds if seconds is not None else days * 86400
    total_samples = total_seconds // interval_sec
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Plot Title", "Feather MC", "", "", "", "Timestamp", "Spd", "Dir", "Temp"])
        ts = start
        for i in range(total_samples):
            w.writerow(["", "", "", f"{3.5 + (i % 50) * 0.1:.1f}", "", ts.strftime("%Y-%m-%d %H:%M:%S"), "", ""])
            ts += timedelta(seconds=interval_sec)
    return total_samples


def write_combine_parts(out_dir: str, num_files: int, rows_per_file: int, start: datetime | None = None) -> list[str]:
    """Write G4-shaped Time History part files (optional preamble before header)."""
    start = start or datetime(2026, 6, 1, 0, 0, 0)
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    ts = start
    header = SPL_HEADER
    for n in range(num_files):
        suffix = "" if n == 0 else f" {n + 1}"
        path = os.path.join(out_dir, f"PARK001_Time History{suffix}.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if n == 1:
                w.writerow(["G4 session metadata"])
                w.writerow(["Export info"])
            w.writerow(header)
            for _ in range(rows_per_file):
                bands = [f"{45.0:.1f}" for _ in BAND_COLS]
                w.writerow(
                    ["SPL", ts.strftime("%Y-%m-%d %H:%M:%S"), "52.3", "54.1", "53.0", "12.4"]
                    + bands
                    + [""]
                )
                ts += timedelta(seconds=1)
        paths.append(path)
    return paths


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic 821 test CSV fixtures")
    parser.add_argument("--out-dir", default=".", help="Output directory")
    parser.add_argument("--days", type=int, default=1)
    parser.add_argument("--seconds", type=int, default=None, help="Override --days with exact row count")
    parser.add_argument("--combine-files", type=int, default=0, help="Also write N combine part files")
    parser.add_argument("--combine-rows", type=int, default=100)
    args = parser.parse_args()

    kwargs = {"seconds": args.seconds} if args.seconds else {}
    spl_path = os.path.join(args.out_dir, "spl.csv")
    met_path = os.path.join(args.out_dir, "met.csv")

    spl_rows = write_spl_csv(spl_path, args.days, **kwargs)
    met_rows = write_met_csv(met_path, args.days, **kwargs)
    print(f"SPL fixture: {spl_path} ({spl_rows:,} rows)")
    print(f"MET fixture: {met_path} ({met_rows:,} samples)")

    if args.combine_files:
        combine_dir = os.path.join(args.out_dir, "combine_parts")
        paths = write_combine_parts(combine_dir, args.combine_files, args.combine_rows)
        print(f"Combine parts: {len(paths)} files in {combine_dir}")


if __name__ == "__main__":
    main()
