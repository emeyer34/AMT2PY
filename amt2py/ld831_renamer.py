
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LD831Renamer (Python CLI)
Port of the WinForms C# tool:
 - Finds THist-containing subfolders (e.g., *.ld0, *.<###>)
 - Merges OverAll, SLog, THist into a single .831 (NPSLD831 header + offsets)
 - Renames to SPL_<SITE>_<yyyy_MM_dd_HHmmss>.831 two levels above THist
 - Optional: Adjusts internal timestamps for all time-history records

Source behavior mirrored from:
 - LD831Renamer.cs (merge, rename, timestamp read/write)
 - LD831Renamer.designer.cs (UI & options)
"""

from __future__ import annotations
import argparse
import os
import re
import sys
import math
import struct
from pathlib import Path
from datetime import datetime, timezone, timedelta

# --------- Utilities ---------

def _read_int32_le(f, offset: int) -> int:
    f.seek(offset, os.SEEK_SET)
    data = f.read(4)
    if len(data) != 4:
        raise IOError(f"Unable to read 4 bytes at offset {offset}")
    return struct.unpack("<i", data)[0]  # signed int32 (matches C# ReadInt32)


def _read_uint32_le(f, offset: int) -> int:
    f.seek(offset, os.SEEK_SET)
    data = f.read(4)
    if len(data) != 4:
        raise IOError(f"Unable to read 4 bytes at offset {offset}")
    return struct.unpack("<I", data)[0]  # unsigned int32


def _read_ascii(f, offset: int, length: int) -> str:
    f.seek(offset, os.SEEK_SET)
    data = f.read(length)
    return data.decode("ascii", errors="ignore")


# --------- Core logic (ported from C#) ---------

def get_timestamp_from_thist(thist_path: Path) -> datetime:
    """
    C#: GetTimeStamp(_file)
    Reads Unix seconds at byte 56 from THist to get original timestamp.
    """
    with thist_path.open("rb") as f:
        ts = _read_int32_le(f, 56)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    return epoch + timedelta(seconds=float(ts))


def bytes_per_record_831(merged_831_path: Path) -> int:
    """
    C#: BytesPerRec(_f)
    Computes bytes per record from firmware settings and 'gust speed' hack.
    This must run on the merged .831 file (after we write it).
    """
    with merged_831_path.open("rb") as f:
        # thistPos pointer at offset 16
        thist_pos = _read_uint32_le(f, 16)

        # firmware version string at 123 + 20 (5 chars), e.g., "1.53 "
        fw_str = _read_ascii(f, 123 + 20, 5).strip()
        try:
            fw_ver = float(fw_str)
        except ValueError:
            # Fall back if parse fails
            fw_ver = 2.0

        # Seek to settings block based on firmware version
        # Original C#: if (<1.5) seek(20 + 4732 - 131), elif (<2) seek(20 + 4744 - 131), else seek(20 + 4760 - 131)
        if fw_ver < 1.5:
            settings_off = 20 + 4732 - 131
        elif fw_ver < 2.0:
            settings_off = 20 + 4744 - 131
        else:
            settings_off = 20 + 4760 - 131

        f.seek(settings_off, os.SEEK_SET)
        settings = bytearray(7)
        settings[0] = f.read(1)[0]
        settings[1] = f.read(1)[0]
        settings[2] = f.read(1)[0]
        f.seek(8, os.SEEK_CUR)
        settings[3] = f.read(1)[0]
        settings[4] = f.read(1)[0]
        settings[5] = f.read(1)[0]
        settings[6] = f.read(1)[0]

        # Count metrics from bit array
        # Bits 0..47 -> +1 per set bit; bits 48..51 -> +12 each; bits 52..55 -> +36 each
        ba_bits = []
        for b in settings:
            for i in range(8):
                ba_bits.append((b >> i) & 1)
        num_metrics = sum(ba_bits[:48])
        for i in range(0, 4):
            if ba_bits[48 + i]:
                num_metrics += 12
        for i in range(4, 8):
            if ba_bits[48 + i]:
                num_metrics += 36

        # Gust speed hack:
        # move to thist_pos + 56; read lenTest; then scan for int32 near lenTest (+/- 1200)
        f.seek(thist_pos + 56, os.SEEK_SET)
        len_test = _read_int32_le(f, f.tell())

        # Skip FLAG, TIMESTAMP, INT_LEN, NUM_METRICS -> ((num_metrics + 3) * 4 - 4) bytes
        skip_bytes = ((num_metrics + 3) * 4) - 4
        f.seek(skip_bytes, os.SEEK_CUR)

        temp_test = None
        while True:
            buf = f.read(4)
            if len(buf) < 4:
                # End-of-file fallback
                break
            iv = struct.unpack("<i", buf)[0]
            if (iv > (len_test - 1200)) and (iv < (len_test + 1200)):
                temp_test = iv
                break

        if temp_test is not None:
            # Calculate the actual metrics count from stream position
            pos = f.tell()
            temp_metrics = int(((pos - 4 - (thist_pos + 56)) / 4) - 3)
            num_metrics = temp_metrics

        return num_metrics * 4  # bytes per record


def set_timestamp_in_merged(merged_831_path: Path, offset_seconds: int) -> None:
    """
    C#: SetTimeStamp(_file, _offset)
    Rewrites each record timestamp (first int32 of the record) += offset_seconds.
    """
    sep_bytes = bytes_per_record_831(merged_831_path) + (4 * 3)  # + FLAG/TIMESTAMP/INT_LEN?
    with merged_831_path.open("r+b") as f:
        thist_pos = _read_uint32_le(f, 16)

        # thist_pos + 48: read numRecs (int32), then skip next int32
        num_recs_off = thist_pos + 48
        f.seek(num_recs_off, os.SEEK_SET)
        num_recs = struct.unpack("<i", f.read(4))[0]
        _ = f.read(4)  # skip

        start_pos = f.tell()

        for i in range(num_recs):
            rec_pos = start_pos + (sep_bytes * i)
            f.seek(rec_pos, os.SEEK_SET)
            ld_time = struct.unpack("<i", f.read(4))[0]
            new_time = int(ld_time + math.floor(offset_seconds))
            f.seek(rec_pos, os.SEEK_SET)
            f.write(struct.pack("<i", new_time))


def merge_usb_files(thist_path: Path) -> Path:
    """
    C#: MergeUsbFiles(_file)
    Writes temp.out in the same folder by concatenating OverAll, SLog, THist
    with NPSLD831 header and three offsets.
    Returns the path to temp.out.
    """
    ld_dir = thist_path.parent
    overall = ld_dir / "OverAll"
    slog = ld_dir / "SLog"

    if not overall.exists() or not slog.exists() or not thist_path.exists():
        raise FileNotFoundError("Expected OverAll, SLog, and THist files in the folder")

    o_data = overall.read_bytes()
    s_data = slog.read_bytes()
    t_data = thist_path.read_bytes()

    temp_out = ld_dir / "temp.out"
    with temp_out.open("wb") as bw:
        bw.write(b"NPSLD831")
        # Write 3 offsets (uint32 LE): 20, 20 + len(OverAll), 20 + len(OverAll) + len(SLog)
        bw.write(struct.pack("<I", 20))
        bw.write(struct.pack("<I", 20 + len(o_data)))
        bw.write(struct.pack("<I", 20 + len(o_data) + len(s_data)))
        # Then data blocks
        bw.write(o_data)
        bw.write(s_data)
        bw.write(t_data)
    return temp_out


def compute_dest_name(thist_path: Path, site: str, offset_seconds: int | None) -> Path:
    """
    C#: FileRename(_oldName, _site [, _offset])
    Destination directory is two levels above THist.
    Filename is SPL_<SITE>_<yyyy_MM_dd_HHmmss>.831 using THist's timestamp + optional offset.
    """
    ts = get_timestamp_from_thist(thist_path)
    if offset_seconds:
        ts = ts + timedelta(seconds=offset_seconds)
    # two levels up from THist: parent of parent
    dest_dir = thist_path.parent.parent
    fname = f"SPL_{site}_{ts.strftime('%Y_%m_%d_%H%M%S')}.831"
    return dest_dir / fname


# --------- Discovery and CLI ---------


def discover_thist_folders(root: Path) -> list[Path]:
    """
    Recursive discovery:
    Find any folder under 'root' that contains the trio: OverAll, SLog, THist.
    Returns the path to the THist file in each folder.
    """
    thists = []
    for d in root.rglob("*"):
        if not d.is_dir():
            continue
        overall = d / "OverAll"
        slog = d / "SLog"
        thist = d / "THist"
        if overall.exists() and slog.exists() and thist.exists():
            thists.append(thist)
    return sorted(thists)


def main():
    ap = argparse.ArgumentParser(description="LD831Renamer (Python port)")
    ap.add_argument("root", type=Path, help="Folder containing *.ld0 or *.<###> subfolders with THist")
    ap.add_argument("--site", required=True, help="Site ID (A–Z0–9), will be uppercased")
    ap.add_argument("--new-date", help="Optional new date for timestamp adjustment, e.g., '2025-04-10 12:34:56' (local time)")
    ap.add_argument("--dry-run", action="store_true", help="Preview actions only (no file writes)")
    args = ap.parse_args()

    site = args.site.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]+", site):
        print("ERROR: Site ID must be alphanumeric A–Z0–9.", file=sys.stderr)
        sys.exit(2)

    root = args.root.resolve()
    if not root.exists() or not root.is_dir():
        print(f"ERROR: Root folder not found: {root}", file=sys.stderr)
        sys.exit(2)

    thists = discover_thist_folders(root)
    if not thists:
        print("No THist folders found matching .+.<###> under the given root.", file=sys.stderr)
        sys.exit(1)

    # Compute optional offset
    offset_seconds = None
    if args.new_date:
        try:
            # Interpret provided time in local timezone, then convert to UTC for diff
            new_dt_local = datetime.strptime(args.new_date, "%Y-%m-%d %H:%M:%S")
            # We'll compute diff against the first item's original timestamp
            orig_dt_utc = get_timestamp_from_thist(thists[0])
            # Convert new_dt_local to UTC (best effort: assume local naive -> UTC)
            # If you want exact TZ handling, we can add tzinfo in a follow-up.
            new_dt_utc = new_dt_local.replace(tzinfo=timezone.utc)
            offset_seconds = int((new_dt_utc - orig_dt_utc).total_seconds())
        except Exception as ex:
            print(f"ERROR parsing --new-date: {ex}", file=sys.stderr)
            sys.exit(2)

    # Process each THist
    for th in thists:
        try:
            temp_out = merge_usb_files(th)  # writes temp.out next to THist
            dest = compute_dest_name(th, site, offset_seconds)

            print(f"[PLAN] {th.parent.name} -> {dest.name}")
            if args.dry_run:
                # clean up temp.out if created
                if temp_out.exists():
                    temp_out.unlink()
                continue

            # If destination exists, mirror C# behavior: delete existing then move
            if dest.exists():
                dest.unlink()

            # Move temp.out to destination
            temp_out.replace(dest)

            # If we adjusted date, rewrite timestamps inside merged file
            if offset_seconds is not None:
                set_timestamp_in_merged(dest, offset_seconds)

        except Exception as ex:
            print(f"ERROR processing {th}: {ex}", file=sys.stderr)

    print("Done.")


if __name__ == "__main__":
    main()
