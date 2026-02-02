
#!/usr/bin/env python3
"""
Compare two text files and write a text report of differences.
"""

# =========================
# CONFIG — EDIT THESE FIRST
# =========================
FILE_A = r"C:\Users\Emeyer\OneDrive - DOI\Desktop\DesktopTemp\NSNSD\Projects\CS_Py\TEST\CANYCOLO_2025\MetricsComp\METRICS_2025_CANYCOLO_AMTonly.txt"        # Path to first file
FILE_B = r"C:\Users\Emeyer\OneDrive - DOI\Desktop\DesktopTemp\NSNSD\Projects\CS_Py\TEST\CANYCOLO_2025\MetricsComp\METRICS_2025_CANYCOLO_py_max_wind.txt"        # Path to second file
OUTPUT_REPORT = r"C:\Users\Emeyer\OneDrive - DOI\Desktop\DesktopTemp\NSNSD\Projects\CS_Py\TEST\CANYCOLO_2025\MetricsComp\AMT_PY_max_wind_diff_report_side_by_side.txt"  # Path for the output report

# Diff style options: "unified" | "context" | "ndiff" | "side_by_side"
DIFF_STYLE = "side_by_side"

# Comparison options
IGNORE_CASE = False                      # Ignore case differences
STRIP_EDGES = False                      # Strip leading/trailing whitespace
COLLAPSE_INTERNAL_WHITESPACE = False     # Collapse multiple spaces/tabs into one
SKIP_BLANK_LINES = False                 # Skip blank lines

# File reading options
ENCODING = "utf-8"                       # File encoding
NEWLINE = None                           # Use universal newline handling
INCLUDE_HEADER = True                    # Include metadata header in report

# Side-by-side diff column widths (only used if DIFF_STYLE == "side_by_side")
SXS_LEFT_WIDTH = 72
SXS_RIGHT_WIDTH = 72

# =========================
# IMPLEMENTATION BELOW
# =========================

import os
import sys
import datetime
import difflib
from typing import List, Tuple

def normalize_line(line: str) -> str:
    if STRIP_EDGES:
        line = line.strip()
    if COLLAPSE_INTERNAL_WHITESPACE:
        import re
        line = re.sub(r"\s+", " ", line)
    if IGNORE_CASE:
        line = line.lower()
    return line

def read_lines(path: str) -> List[str]:
    with open(path, "r", encoding=ENCODING, newline=NEWLINE) as f:
        raw_lines = f.readlines()
    normalized = []
    for ln in raw_lines:
        content = ln.rstrip("\n")
        content = normalize_line(content)
        if SKIP_BLANK_LINES and content == "":
            continue
        normalized.append(content + "\n")
    return normalized

def file_metadata(path: str) -> Tuple[str, int, str]:
    abspath = os.path.abspath(path)
    try:
        st = os.stat(path)
        size = st.st_size
        mtime = datetime.datetime.fromtimestamp(st.st_mtime).isoformat()
    except FileNotFoundError:
        size = -1
        mtime = "N/A"
    return abspath, size, mtime

def make_header() -> str:
    a_path, a_size, a_mtime = file_metadata(FILE_A)
    b_path, b_size, b_mtime = file_metadata(FILE_B)
    now = datetime.datetime.now().isoformat()
    lines = [
        "==================== DIFF REPORT ====================",
        f"Generated: {now}",
        f"Diff style: {DIFF_STYLE}",
        "",
        "File A:",
        f"  Path: {a_path}",
        f"  Size: {a_size} bytes",
        f"  Modified: {a_mtime}",
        "",
        "File B:",
        f"  Path: {b_path}",
        f"  Size: {b_size} bytes",
        f"  Modified: {b_mtime}",
        "=====================================================",
        "",
    ]
    return "\n".join(lines)

def side_by_side_diff(a_lines: List[str], b_lines: List[str]) -> List[str]:
    sm = difflib.SequenceMatcher(None, a_lines, b_lines)
    out_lines: List[str] = []
    sep = " | "

    def fmt(s: str, width: int) -> str:
        s = s.rstrip("\n")
        if len(s) > width:
            return s[: max(0, width - 1)] + "…"
        return s.ljust(width)

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i1, i2):
                left = fmt(a_lines[k], SXS_LEFT_WIDTH)
                right = fmt(b_lines[j1 + (k - i1)], SXS_RIGHT_WIDTH)
                out_lines.append(f"  {left}{sep}{right}\n")
        elif tag == "delete":
            for k in range(i1, i2):
                left = fmt(a_lines[k], SXS_LEFT_WIDTH)
                out_lines.append(f"- {left}{sep}{' '.ljust(SXS_RIGHT_WIDTH)}\n")
        elif tag == "insert":
            for k in range(j1, j2):
                right = fmt(b_lines[k], SXS_RIGHT_WIDTH)
                out_lines.append(f"+ {' '.ljust(SXS_LEFT_WIDTH)}{sep}{right}\n")
        elif tag == "replace":
            span_len = max(i2 - i1, j2 - j1)
            for offset in range(span_len):
                left = fmt(a_lines[i1 + offset], SXS_LEFT_WIDTH) if i1 + offset < i2 else ' '.ljust(SXS_LEFT_WIDTH)
                right = fmt(b_lines[j1 + offset], SXS_RIGHT_WIDTH) if j1 + offset < j2 else ' '.ljust(SXS_RIGHT_WIDTH)
                out_lines.append(f"! {left}{sep}{right}\n")
    return out_lines

def generate_diff() -> List[str]:
    a_lines = read_lines(FILE_A)
    b_lines = read_lines(FILE_B)
    style = DIFF_STYLE.lower()
    if style == "unified":
        return list(difflib.unified_diff(a_lines, b_lines, fromfile=os.path.basename(FILE_A), tofile=os.path.basename(FILE_B), lineterm=""))
    elif style == "context":
        return list(difflib.context_diff(a_lines, b_lines, fromfile=os.path.basename(FILE_A), tofile=os.path.basename(FILE_B), lineterm=""))
    elif style == "ndiff":
        return list(difflib.ndiff(a_lines, b_lines))
    elif style == "side_by_side":
        return side_by_side_diff(a_lines, b_lines)
    else:
        raise ValueError(f"Unknown diff style: {DIFF_STYLE}")

def write_report(diff_lines: List[str]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(OUTPUT_REPORT)), exist_ok=True)
    with open(OUTPUT_REPORT, "w", encoding="utf-8", newline="\n") as f:
        if INCLUDE_HEADER:
            f.write(make_header())
        if not diff_lines:
            f.write("No differences found.\n")
        else:
            for ln in diff_lines:
                f.write(ln if ln.endswith("\n") else ln + "\n")

def main():
    if not os.path.isfile(FILE_A) or not os.path.isfile(FILE_B):
        print("Error: One or both input files not found.", file=sys.stderr)
        sys.exit(1)
    diff_lines = generate_diff()
    write_report(diff_lines)
    print(f"Diff report written to: {OUTPUT_REPORT}")
    if not diff_lines:
        print("No differences found.")
    else:
        print(f"Diff style used: {DIFF_STYLE}")

if __name__ == "__main__":
    main()