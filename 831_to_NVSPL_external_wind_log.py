
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Larson Davis 831 (.831) -> NVSPL hourly .txt converter

- Mirrors Conversion.cs (LD831 + LD831NEW parsing)
- Adds flexible MET (wind) merge from CSV:
    * encoding + delimiter sniff (UTF-8/UTF-16)
    * robust delimiter detection (Sniffer + fallback for \t, ',', ';')
    * flexible timestamp parsing (seconds/no-seconds, AM/PM, ISO) with regex extraction
    * explicit bin-repetition ("bin" method) across 1s NVSPL records
- Diagnostics:
    * MET load stats (headers/short rows/time fails/wind fails)
    * MET/NVSPL time ranges + overlap
    * inferred MET sample interval
    * merge counts
"""

from __future__ import annotations
import datetime as dt
import math
import struct
import csv
import bisect
import sys
import io
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

# --- SAFELY raise CSV field-size limit (Windows C long is 32-bit) ---
try:
    csv.field_size_limit(min(sys.maxsize, 2_147_483_647))
except Exception:
    csv.field_size_limit(2_147_483_647)

# --- USER CONFIGURATION (edit these as needed) ---
INPUT_PATH = r"C:\Users\Emeyer\OneDrive - DOI\Desktop\DesktopTemp\NSNSD\Projects\CS_Py\TEST\CANYCOLO_2025\Python_Process\SPL"
OUTPUT_PATH = r"C:\Users\Emeyer\OneDrive - DOI\Desktop\DesktopTemp\NSNSD\Projects\CS_Py\TEST\CANYCOLO_2025\Python_Process\Python_no_wind\NVSPL"
CREATE_SITE_FOLDERS = False   # per-site subfolders
RECURSIVE = False             # recurse subfolders for .831

# ---- MET MERGE (Wind) ----
MERGE_MET = False
MET_CSV_PATH = r"C:\Users\Emeyer\OneDrive - DOI\Desktop\DesktopTemp\NSNSD\Projects\CS_Py\TEST\CANYCOLO_2025\Met\CANY_COLO_Lathrop.csv"

# Column indices (0-based): 0=index, 1=DateTime, 2=Avg m/s, 3=Gust m/s, 4=Dir
MET_TIME_COL = 1
MET_WIND_COL = 3              # set to 3 if you want Gust/Max instead

# Timestamp format in the CSV; None = flexible parse (seconds/no-seconds, AM/PM, ISO)
MET_DT_FORMAT = None

# Timezone alignment (keeps NVSPL output in local Mountain time)
LD_TZ  = None # "America/Denver" for ex. if in UTC
MET_TZ = None # "America/Denver" for ex. if in UTC

# Units
WIND_UNITS = "mps"            # "mps" or "mph"
CONVERT_MPH_TO_MPS = False    # True only if WIND_UNITS=="mph"

# Merge method and bin interpretation
FILL_METHOD = "bin"           # "bin" (repeat across sampling bin), "forward", or "nearest"
MET_SAMPLE_STAMP = "end"    # how CSV timestamps represent bin: "start" | "center" | "end"
BACKFILL_BEFORE_FIRST = False # fill seconds before first MET sample?
NEAREST_TOLERANCE_SEC = 90    # only used for "nearest"
OVERWRITE_EXISTING_WIND = True
# -----------------------------------------------
# Optional timezone handling
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:
    ZoneInfo = None

def _tz(name: Optional[str]) -> Optional[dt.tzinfo]:
    if not name:
        return None
    if ZoneInfo is None:
        raise RuntimeError("zoneinfo not available; upgrade Python or install tzdata.")
    return ZoneInfo(name)

# ---------- Filename time parser ----------
# Expected patterns (examples):
#   SPL_CANYCOLO_2025_05_15_112147
#   SPL_<SITE>_<YYYY>_<MM>_<DD>_<HHMMSS>
_filename_re = re.compile(
    r"""^SPL_(?P<site>[A-Za-z0-9]+)_(?P<Y>\d{4})_(?P<M>\d{2})_(?P<D>\d{2})_(?P<hms>\d{6})$""",
    re.VERBOSE
)

def _dt_from_filename(stem: str) -> Optional[dt.datetime]:
    m = _filename_re.match(stem)
    if not m:
        return None
    Y = int(m.group("Y"))
    M = int(m.group("M"))
    D = int(m.group("D"))
    hms = m.group("hms")
    HH = int(hms[0:2]); MM = int(hms[2:4]); SS = int(hms[4:6])
    return dt.datetime(Y, M, D, HH, MM, SS)  # naive local wall time anchor

# ---------- NVSPL columns ----------
NVSPL_HEADER = [
    "SiteID","STime",
    "H12p5","H15p8","H20","H25","H31p5","H40","H50","H63","H80","H100","H125","H160","H200","H250","H315",
    "H400","H500","H630","H800","H1000","H1250","H1600","H2000","H2500","H3150","H4000","H5000","H6300","H8000",
    "H10000","H12500","H16000","H20000",
    "dbA","dbC","dbF","Voltage","WindSpeed","WindDir","TempIns","TempOut","Humidity",
    "INVID","INSID","GChar1","GChar2","GChar3","AdjustmentsApplied","CalibrationAdjustment",
    "GPSTimeAdjustment","GainAdjustment","Status"
]
UNIX_EPOCH = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)

def _fmt_ts(ts: dt.datetime) -> str:
    return ts.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

def _status_from_flag(test_flag: int) -> str:
    idx = test_flag // 1024
    return ["0","9901","9910","9911"][idx] if 0 <= idx < 4 else ""

def _log10_db(power: float) -> str:
    if power <= 0:
        return ""
    return f"{round(10.0 * math.log10(power), 1):.1f}"

def _round1(x: float) -> str:
    return f"{round(x, 1):.1f}"

def _maybe_localize_unix_seconds(sec: int, ld_tz: Optional[str]) -> dt.datetime:
    """
    Default: treat epoch seconds as local wall-clock (naive).
    NOTE: We will *anchor* to filename later, so any small bias will be corrected.
    """
    return dt.datetime.fromtimestamp(sec).replace(tzinfo=None)

# ---------- LD831 legacy format ("LD831") ----------
def parse_ld831_old(path: Path) -> Iterable[Dict[str, str]]:
    with path.open("rb") as f:
        data = f.read()

    def read_i32_at(o: int) -> Tuple[int, int]:
        return struct.unpack_from("<i", data, o)[0], o + 4
    def read_f32_at(o: int) -> Tuple[float, int]:
        return struct.unpack_from("<f", data, o)[0], o + 4

    numRecs, _ = read_i32_at(48)
    currSec, pos = read_i32_at(56)

    while pos < len(data):
        val, pos = read_i32_at(pos)
        if val == currSec:
            break

    dataLen = pos - 8 - 56 + 4
    numFields = (dataLen // 4) - 3

    if numRecs < 0:
        numRecs = 0
    if numRecs > 172800:
        numRecs = numRecs - 60
    if ((numRecs * (numFields + 3) * 4) + 52) > len(data):
        numRecs = int((len(data) - 52) / ((numFields + 3) * 4)) - 5

    pos -= 8
    prev_dt = dt.datetime(1980, 1, 23)

    for _ in range(max(0, numRecs - 1)):
        testFlag, pos = read_i32_at(pos)
        if testFlag in (0, 1024, 2048, 3072):
            sec, pos = read_i32_at(pos)
            _, pos = read_f32_at(pos)  # duration skip
            dtstamp = _maybe_localize_unix_seconds(sec, LD_TZ)
            if dtstamp > prev_dt:
                row: Dict[str, str] = {k: "" for k in NVSPL_HEADER}
                row["SiteID"] = path.stem.split("_")[1] if "_" in path.stem else ""
                row["STime"] = _fmt_ts(dtstamp)
                if numFields == 39:
                    la_power, pos = read_f32_at(pos); row["dbA"] = _log10_db(la_power)
                    voltage, pos = read_f32_at(pos); row["Voltage"] = _round1(voltage)
                    tint, pos = read_f32_at(pos); row["TempIns"] = _round1(tint)
                elif numFields > 36:
                    la_power, pos = read_f32_at(pos); row["dbA"] = _log10_db(la_power)
                    pos += (numFields - 37) * 4
                    for _i in range(3):  # skip 6.5, 8.0, 10.0 Hz
                        _, pos = read_f32_at(pos)
                    ob_names = NVSPL_HEADER[2:2+33]
                    for name in ob_names:
                        pwr, pos = read_f32_at(pos)
                        row[name] = _log10_db(pwr)
                if testFlag == 2048:
                    row["GChar1"] = "OVL:OBA"
                elif testFlag == 3072:
                    row["GChar1"] = "OVL:SLMOBA"
                elif testFlag == 1024:
                    row["GChar1"] = "OVL:SLM"
                row["Status"] = _status_from_flag(testFlag)
                prev_dt = dtstamp
                yield row
            else:
                pos += numFields * 4
        else:
            pos += (numFields + 2) * 4

# ---------- LD831 NEW format ("NPSLD831") ----------
def parse_ld831_new(path: Path) -> Iterable[Dict[str, str]]:
    with path.open("rb") as f:
        data = f.read()

    def read_i32_at(o: int) -> Tuple[int, int]:
        return struct.unpack_from("<i", data, o)[0], o + 4
    def read_u32_at(o: int) -> Tuple[int, int]:
        return struct.unpack_from("<I", data, o)[0], o + 4
    def read_f32_at(o: int) -> Tuple[float, int]:
        return struct.unpack_from("<f", data, o)[0], o + 4
    def read_byte_at(o: int) -> Tuple[int, int]:
        return data[o], o + 1
    def read_chars(o: int, n: int) -> Tuple[str, int]:
        raw = data[o:o+n]
        try:
            s = raw.decode("ascii", errors="ignore")
        except Exception:
            s = "".join(chr(b) for b in raw if 32 <= b < 127)
        return s, o + n

    thistPos, _ = read_u32_at(16)
    sn, _ = read_chars(66, 5); sn = sn.strip("\x00")
    fw_str, _ = read_chars(143, 5)
    try:
        fw = float(fw_str)
    except Exception:
        fw = 0.0

    if fw < 1.5:
        settings_pos = 20 + 4732 - 131
    elif fw < 2.0:
        settings_pos = 20 + 4744 - 131
    else:
        settings_pos = 20 + 4760 - 131

    pos = settings_pos
    settings = []
    b, pos = read_byte_at(pos); settings.append(b)
    b, pos = read_byte_at(pos); settings.append(b)
    b, pos = read_byte_at(pos); settings.append(b)
    pos += 8
    b, pos = read_byte_at(pos); settings.append(b)
    b, pos = read_byte_at(pos); settings.append(b)
    b, pos = read_byte_at(pos); settings.append(b)
    b, pos = read_byte_at(pos); settings.append(b)

    bits: List[bool] = []
    for byte in settings:
        for i in range(8):
            bits.append(bool((byte >> i) & 1))

    numMetrics = 0
    idxLAEQ = idxLCEQ = idxLZEQ = -1
    idxEXTV = idxETMP = idxITMP = -1
    idxWSPD = idxGDIR = idxCHNB = -1
    idxZOBA11 = idxZOBA13 = -1

    for i in range(48):
        if i == 2 and bits[i]: idxLAEQ = numMetrics
        elif i == 13 and bits[i]: idxLCEQ = numMetrics
        elif i == 24 and bits[i]: idxLZEQ = numMetrics
        elif i == 36 and bits[i]: idxEXTV = numMetrics
        elif i == 37 and bits[i]: idxITMP = numMetrics
        elif i == 40 and bits[i]: idxWSPD = numMetrics
        elif i == 41 and bits[i]: idxGDIR = numMetrics
        elif i == 42 and bits[i]: idxETMP = numMetrics
        elif i == 43 and bits[i]: idxCHNB = numMetrics
        if bits[i]:
            numMetrics += 1

    for i in range(4):
        if (48 + i) == 49 and bits[48 + i]:
            idxZOBA11 = numMetrics
        if bits[48 + i]:
            numMetrics += 12

    for i in range(4, 8):
        if (48 + i) == 53 and bits[48 + i]:
            idxZOBA13 = numMetrics
        if bits[48 + i]:
            numMetrics += 36

    if idxLAEQ == -1:
        if fw < 1.5:
            pos = 20 + 4732 - 131 - 1
        elif fw < 2.0:
            pos = 20 + 4744 - 131 - 1
        else:
            pos = 20 + 4760 - 131 - 1
        b, _ = read_byte_at(pos)
        if ((b >> 0) & 1):
            idxLAEQ = 0
            numMetrics += 1

    pos = 7960 + 20
    gain_byte, _ = read_byte_at(pos)
    pos = 8029 + 20
    oba_byte, _ = read_byte_at(pos)

    gainVal = "0" if (gain_byte & (1 << 0)) else "20"
    obaRange = "OBAnorm" if (oba_byte & (1 << 0)) else "OBAlow"

    pos = thistPos + 56
    len_test, pos = read_i32_at(pos)
    pos += (numMetrics + 3) * 4 - 4
    _temp = 0
    while pos + 4 <= len(data):
        _temp, pos = read_i32_at(pos)
        if (len_test - 2400) < _temp < (len_test + 2400):
            break
    _temp = ((pos - 4) - (thistPos + 56)) // 4 - 3
    if idxWSPD == -1 and idxGDIR != -1 and _temp > numMetrics:
        idxWSPD = _temp - 1
    numMetrics = _temp

    pos = thistPos + 48
    numRecs, pos = read_i32_at(pos)

    if numRecs < 0:
        numRecs = 0
    if numRecs > 172800:
        numRecs = numRecs - 60
    if (( (numRecs * (numMetrics + 3) * 4) ) + 52 + thistPos) > len(data):
        numRecs = int((len(data) - thistPos - 52) / ((numMetrics + 3) * 4)) - 5

    slmInfo = f"LD831_{sn}v{fw:.3f}"
    prev_dt = dt.datetime(1980, 1, 23)
    pos = thistPos + 52

    for _ in range(max(0, numRecs)):
        testFlag, pos = read_i32_at(pos)
        if testFlag in (0, 1024, 2048, 3072):
            sec, pos = read_i32_at(pos)
            pos += 4  # skip duration

            dtstamp = _maybe_localize_unix_seconds(sec, LD_TZ)
            if dtstamp > prev_dt:
                vals: List[float] = []
                for _j in range(numMetrics):
                    v, pos = read_f32_at(pos)
                    vals.append(v)

                row: Dict[str, str] = {k: "" for k in NVSPL_HEADER}
                row["SiteID"] = path.stem.split("_")[1] if "_" in path.stem else ""
                row["STime"] = _fmt_ts(dtstamp)

                # scalar metrics
                if idxLAEQ != -1 and idxLAEQ < len(vals):
                    row["dbA"] = _log10_db(vals[idxLAEQ])
                if idxLCEQ != -1 and idxLCEQ < len(vals):
                    row["dbC"] = _log10_db(vals[idxLCEQ])
                if idxLZEQ != -1 and idxLZEQ < len(vals):
                    row["dbF"] = _log10_db(vals[idxLZEQ])
                if idxEXTV != -1 and idxEXTV < len(vals):
                    row["Voltage"] = _round1(vals[idxEXTV])
                if idxITMP != -1 and idxITMP < len(vals):
                    row["TempIns"] = _round1(vals[idxITMP])
                if idxETMP != -1 and idxETMP < len(vals):
                    row["TempOut"] = _round1(vals[idxETMP])
                if idxWSPD != -1 and idxWSPD < len(vals):
                    row["WindSpeed"] = _round1(vals[idxWSPD])
                if idxGDIR != -1 and idxGDIR < len(vals):
                    row["WindDir"] = _round1(vals[idxGDIR])
                if idxCHNB != -1 and idxCHNB < len(vals):
                    h = ((round(0.01 * vals[idxCHNB], 2) / 2.69) - 0.1515) / 0.00636
                    if idxETMP != -1 and idxETMP < len(vals):
                        h = h / (1.0546 - 0.00216 * round(vals[idxETMP], 1))
                    row["Humidity"] = f"{round(h, 1):.1f}"

                # one-octave (11 bands)
                if idxZOBA11 != -1 and (idxZOBA11 + 11) < len(vals) + 1:
                    bands11 = [
                        ("H15p8", 1), ("H31p5", 2), ("H63", 3), ("H125", 4), ("H250", 5),
                        ("H500", 6), ("H1000", 7), ("H2000", 8), ("H4000", 9),
                        ("H8000", 10), ("H16000", 11)
                    ]
                    for name, offset in bands11:
                        row[name] = _log10_db(vals[idxZOBA11 + offset])

                # 1/3-octave (33 bands)
                if idxZOBA13 != -1 and (idxZOBA13 + 36) <= len(vals):
                    ob_names = NVSPL_HEADER[2:2+33]
                    for j, name in enumerate(ob_names):
                        row[name] = _log10_db(vals[idxZOBA13 + (3 + j)])

                row["Status"] = _status_from_flag(testFlag)
                row["GChar3"] = slmInfo
                row["GChar1"] = obaRange
                row["GainAdjustment"] = gainVal

                prev_dt = dtstamp
                yield row
            else:
                pos += numMetrics * 4
        else:
            pos += (numMetrics + 2) * 4

# ---------- Detection wrapper ----------
def is_ld831_new(path: Path) -> bool:
    with path.open("rb") as f:
        magic = f.read(8)
    return magic == b"NPSLD831"

def parse_ld831(path: Path) -> Iterable[Dict[str, str]]:
    return parse_ld831_new(path) if is_ld831_new(path) else parse_ld831_old(path)

# ---------- Hour bucketing & writing ----------
def bucket_by_hour(rows: Iterable[Dict[str, str]]) -> Dict[Tuple[str, dt.datetime], List[Dict[str, str]]]:
    buckets: Dict[Tuple[str, dt.datetime], List[Dict[str, str]]] = {}
    for r in rows:
        site = r["SiteID"]
        t = dt.datetime.strptime(r["STime"], "%Y-%m-%d %H:%M:%S.%f")
        hour_start = t.replace(minute=0, second=0, microsecond=0)
        buckets.setdefault((site, hour_start), []).append(r)
    return buckets

def write_nvspl_hour(out_dir: Path, site: str, hour: dt.datetime, rows: List[Dict[str, str]]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"NVSPL_{site}_{hour.strftime('%Y_%m_%d_%H')}.txt"
    out_path = out_dir / fname
    rows = sorted(rows, key=lambda r: r["STime"])
    with out_path.open("w", encoding="utf-8", newline="") as w:
        w.write(",".join(NVSPL_HEADER) + "\n")
        for r in rows:
            w.write(",".join(r.get(col, "") or "" for col in NVSPL_HEADER) + "\n")
    return out_path

# ---------- MET CSV LOADER & MERGER (encoding + delimiter sniff; bin-repeat) ----------
def _extract_dt_string(s: str) -> Optional[str]:
    if not s:
        return None
    s = s.replace("\ufeff", "").replace("\xa0", " ").strip().strip('"').strip("'")
    m = re.search(
        r'(?P<mdy>\b\d{1,2}/\d{1,2}/\d{2,4})\s+'
        r'(?P<hms>\d{1,2}:\d{2}(?::\d{2})?)\s*(?P<ampm>\bAM\b|\bPM\b|\bam\b|\bpm\b)?',
        s
    )
    if m:
        dt_str = f"{m.group('mdy')} {m.group('hms')}"
        if m.group('ampm'):
            dt_str += f" {m.group('ampm').upper()}"
        return dt_str
    m = re.search(
        r'(?P<iso>\b\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?)(?:Z|[+\-]\d{2}:\d{2})?',
        s
    )
    if m:
        return m.group('iso')
    m = re.search(
        r'(?P<dmy>\b\d{1,2}/\d{1,2}/\d{2,4})\s+(?P<hms>\d{1,2}:\d{2}(?::\d{2})?)\s*(?P<ampm>\bAM\b|\bPM\b|\bam\b|\bpm\b)?',
        s
    )
    if m:
        dt_str = f"{m.group('dmy')} {m.group('hms')}"
        if m.group('ampm'):
            dt_str += f" {m.group('ampm').upper()}"
        return dt_str
    return None

def _parse_dt_flex(s: str, fmt: Optional[str]) -> Optional[dt.datetime]:
    s = (s or "").strip()
    if not s:
        return None
    if fmt:
        try:
            return dt.datetime.strptime(s, fmt)
        except Exception:
            pass
    core = _extract_dt_string(s)
    if not core:
        return None
    for cand in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M",
                 "%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %I:%M %p",
                 "%m/%d/%y %H:%M:%S", "%m/%d/%y %H:%M",
                 "%m/%d/%y %I:%M:%S %p", "%m/%d/%y %I:%M %p"):
        try:
            return dt.datetime.strptime(core, cand)
        except Exception:
            continue
    for cand in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
                 "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f",
                 "%Y-%m-%dT%H:%M"):
        try:
            return dt.datetime.strptime(core, cand)
        except Exception:
            continue
    return None

def _align_naive(ts: dt.datetime, src_tz: Optional[str], dst_tz: Optional[str]) -> dt.datetime:
    if src_tz and dst_tz:
        tz_src = _tz(src_tz); tz_dst = _tz(dst_tz)
        return ts.replace(tzinfo=tz_src).astimezone(tz_dst).replace(tzinfo=None)
    elif src_tz and not dst_tz:
        tz_src = _tz(src_tz)
        return ts.replace(tzinfo=tz_src).astimezone(dt.timezone.utc).replace(tzinfo=None)
    else:
        return ts.replace(tzinfo=None)

def _sniff_encoding(csv_path: Path) -> str:
    enc = "utf-8"
    try:
        with csv_path.open("rb") as fb:
            head = fb.read(4)
            if head.startswith(b"\xff\xfe"):
                enc = "utf-16-le"
            elif head.startswith(b"\xfe\xff"):
                enc = "utf-16-be"
            elif head.startswith(b"\xef\xbb\xbf"):
                enc = "utf-8-sig"
    except Exception:
        pass
    return enc

def _sniff_delimiter_with_sniffer(sample_text: str) -> Optional[str]:
    try:
        dialect = csv.Sniffer().sniff(sample_text, delimiters="\t,;")
        return dialect.delimiter
    except Exception:
        return None

def _try_load(csv_path: Path,
              encoding: str,
              delimiter: str,
              time_col: int,
              wind_col: int,
              dt_format: Optional[str],
              src_tz: Optional[str],
              dst_tz: Optional[str],
              units: str,
              convert_mph_to_mps: bool) -> Tuple[List[Tuple[dt.datetime, float]], Dict[str, int]]:

    stats = {"header_skips": 0, "short_rows": 0, "time_parse_fail": 0, "wind_parse_fail": 0, "parsed_rows": 0}
    out: List[Tuple[dt.datetime, float]] = []
    if not csv_path.exists():
        return out, stats

    with csv_path.open("r", encoding=encoding, newline="") as f:
        reader = csv.reader(f, delimiter=delimiter)
        for row in reader:
            if not row:
                continue
            if len(row) == 1 and "Plot Title" in row[0]:
                stats["header_skips"] += 1
                continue
            if row[0].strip().startswith("#"):
                stats["header_skips"] += 1
                continue
            if len(row) <= max(time_col, wind_col):
                stats["short_rows"] += 1
                continue

            t_raw = row[time_col]
            w_raw = row[wind_col]

            if any(k in t_raw for k in ("Date", "Time", "GMT", "UTC")):
                stats["header_skips"] += 1
                continue

            t = _parse_dt_flex(t_raw, dt_format)
            if t is None:
                stats["time_parse_fail"] += 1
                continue
            t = _align_naive(t, src_tz, dst_tz)

            try:
                w = float(str(w_raw).strip())
            except Exception:
                stats["wind_parse_fail"] += 1
                continue

            if units.lower() == "mph" and convert_mph_to_mps:
                w = w * 0.44704

            out.append((t, w))
            stats["parsed_rows"] += 1

    out.sort(key=lambda x: x[0])
    return out, stats

def _manual_fallback_read(csv_path: Path,
                          encoding: str,
                          candidate_delims: List[str],
                          time_col: int,
                          wind_col: int,
                          dt_format: Optional[str],
                          src_tz: Optional[str],
                          dst_tz: Optional[str],
                          units: str,
                          convert_mph_to_mps: bool) -> Tuple[List[Tuple[dt.datetime, float]], Dict[str, int]]:
    stats = {"header_skips": 0, "short_rows": 0, "time_parse_fail": 0, "wind_parse_fail": 0, "parsed_rows": 0}
    out: List[Tuple[dt.datetime, float]] = []
    norm_space = re.compile(r"[ \ufeff]")  # NBSP + BOM inside lines
    with csv_path.open("r", encoding=encoding, errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if "Plot Title" in line or line.startswith("#"):
                stats["header_skips"] += 1
                continue
            line = norm_space.sub(" ", line)

            row = None
            for d in candidate_delims:
                if d not in line:
                    continue
                reader = csv.reader(io.StringIO(line), delimiter=d)
                try:
                    row = next(reader)
                except Exception:
                    row = None
                if row and len(row) > max(time_col, wind_col):
                    break

            if not row:
                stats["short_rows"] += 1
                continue

            t_raw = row[time_col]
            w_raw = row[wind_col]

            if any(k in t_raw for k in ("Date", "Time", "GMT", "UTC")):
                stats["header_skips"] += 1
                continue

            t = _parse_dt_flex(t_raw, dt_format)
            if t is None:
                stats["time_parse_fail"] += 1
                continue
            t = _align_naive(t, src_tz, dst_tz)

            try:
                w = float(str(w_raw).strip())
            except Exception:
                stats["wind_parse_fail"] += 1
                continue

            if units.lower() == "mph" and convert_mph_to_mps:
                w = w * 0.44704

            out.append((t, w))
            stats["parsed_rows"] += 1

    out.sort(key=lambda x: x[0])
    return out, stats

def load_met_csv(csv_path: Path,
                 time_col: int,
                 wind_col: int,
                 dt_format: Optional[str],
                 src_tz: Optional[str],
                 dst_tz: Optional[str],
                 units: str,
                 convert_mph_to_mps: bool) -> List[Tuple[dt.datetime, float]]:
    enc = _sniff_encoding(csv_path)

    sample_bytes = b""
    try:
        with csv_path.open("rb") as fb:
            sample_bytes = fb.read(65536)
    except Exception:
        pass

    sample_text = ""
    try:
        sample_text = sample_bytes.decode(enc, errors="replace")
    except Exception:
        sample_text = sample_bytes.decode("utf-8", errors="replace")

    sniffed_delim = _sniff_delimiter_with_sniffer(sample_text) or ("\t" if "\t" in sample_text else ("," if "," in sample_text else ";"))
    print(f"[MET] Sniffed encoding={enc}, delimiter={repr(sniffed_delim)}")

    samples, stats = _try_load(csv_path, enc, sniffed_delim, time_col, wind_col,
                               dt_format, src_tz, dst_tz, units, convert_mph_to_mps)
    print(f"[MET] Attempt enc={enc}, delim={repr(sniffed_delim)} -> parsed {stats['parsed_rows']} rows "
          f"(headers: {stats['header_skips']}, short: {stats['short_rows']}, "
          f"time fails: {stats['time_parse_fail']}, wind fails: {stats['wind_parse_fail']})")

    if stats["parsed_rows"] == 0:
        for alt in [",", "\t", ";"]:
            if alt == sniffed_delim:
                continue
            samples2, stats2 = _try_load(csv_path, enc, alt, time_col, wind_col,
                                         dt_format, src_tz, dst_tz, units, convert_mph_to_mps)
            print(f"[MET] Attempt enc={enc}, delim={repr(alt)} -> parsed {stats2['parsed_rows']} rows "
                  f"(headers: {stats2['header_skips']}, short: {stats2['short_rows']}, "
                  f"time fails: {stats2['time_parse_fail']}, wind fails: {stats2['wind_parse_fail']})")
            if stats2["parsed_rows"] > stats["parsed_rows"]:
                samples, stats, sniffed_delim = samples2, stats2, alt
        print(f"[MET] Auto-selected delimiter {repr(sniffed_delim)}")

    if stats["parsed_rows"] == 0:
        for enc_alt in ("utf-8", "utf-8-sig", "utf-16-le", "utf-16-be"):
            if enc_alt == enc:
                continue
            samples3, stats3 = _try_load(csv_path, enc_alt, sniffed_delim, time_col, wind_col,
                                         dt_format, src_tz, dst_tz, units, convert_mph_to_mps)
            print(f"[MET] Attempt enc={enc_alt}, delim={repr(sniffed_delim)} -> parsed {stats3['parsed_rows']} rows "
                  f"(headers: {stats3['header_skips']}, short: {stats3['short_rows']}, "
                  f"time fails: {stats3['time_parse_fail']}, wind fails: {stats3['wind_parse_fail']})")
            if stats3["parsed_rows"] > stats["parsed_rows"]:
                samples, stats, enc = samples3, stats3, enc_alt
        print(f"[MET] Auto-selected encoding {enc}")

    if stats["parsed_rows"] == 0:
        print("[MET] Switching to manual fallback reader ...")
        samples4, stats4 = _manual_fallback_read(csv_path, enc, candidate_delims=["\t", ",", ";"],
                                                 time_col=time_col, wind_col=wind_col,
                                                 dt_format=dt_format, src_tz=src_tz, dst_tz=dst_tz,
                                                 units=units, convert_mph_to_mps=convert_mph_to_mps)
        print(f"[MET] Fallback parsed {stats4['parsed_rows']} rows "
              f"(headers: {stats4['header_skips']}, short: {stats4['short_rows']}, "
              f"time fails: {stats4['time_parse_fail']}, wind fails: {stats4['wind_parse_fail']})")
        if stats4["parsed_rows"] > stats["parsed_rows"]:
            samples, stats = samples4, stats4

    if samples:
        print(f"[MET] Loaded {len(samples)} samples. First 3:", [
            (samples[i][0].strftime("%Y-%m-%d %H:%M:%S"), round(samples[i][1], 3))
            for i in range(min(3, len(samples)))
        ])
    else:
        print("[MET] Still parsed 0 samples. Please share 3–5 actual data lines so we can tailor parsing precisely.")
    return samples

# ---- Bin-repeat merging ----
def _infer_interval_seconds(met_times: List[dt.datetime]) -> int:
    if len(met_times) < 2:
        return 1
    deltas = [(met_times[i] - met_times[i-1]).total_seconds() for i in range(1, len(met_times))]
    deltas = [d for d in deltas if d > 0]
    if not deltas:
        return 1
    deltas.sort()
    mid = len(deltas) // 2
    median = deltas[mid] if len(deltas) % 2 == 1 else (deltas[mid-1] + deltas[mid]) / 2.0
    for cand in (1, 2, 5, 10, 15, 20, 30, 60, 120, 300):
        if abs(median - cand) <= 0.6:
            return cand
    return int(round(median))

def _shift_times_for_stamp(met_times: List[dt.datetime], interval_sec: int, stamp: str) -> List[dt.datetime]:
    if interval_sec <= 0 or (stamp or "start").lower() == "start":
        return met_times
    s = (stamp or "start").lower()
    shift = 0
    if s == "center":
        shift = interval_sec / 2.0
    elif s == "end":
        shift = interval_sec
    if shift == 0:
        return met_times
    return [t - dt.timedelta(seconds=shift) for t in met_times]

def merge_wind_into_rows(rows: List[Dict[str, str]],
                         met_samples: List[Tuple[dt.datetime, float]],
                         method: str,
                         tolerance_sec: int,
                         overwrite: bool,
                         sample_stamp: str = "start",
                         backfill_before_first: bool = False) -> int:
    updated = 0
    if not met_samples or not rows:
        return updated

    nvspl_times = [dt.datetime.strptime(r["STime"], "%Y-%m-%d %H:%M:%S.%f") for r in rows]
    met_times = [t for (t, _) in met_samples]
    met_vals = [v for (_, v) in met_samples]

    interval = _infer_interval_seconds(met_times)
    met_times_shifted = _shift_times_for_stamp(met_times, interval, sample_stamp)

    print(f"[MERGE] Method={method}, inferred MET interval={interval}s, stamp={sample_stamp}, backfill={backfill_before_first}")
    print(f"[MERGE] First 3 shifted MET times:", [met_times_shifted[i].strftime("%Y-%m-%d %H:%M:%S") for i in range(min(3, len(met_times_shifted)))])

    if method.lower() == "bin":
        bins_start = met_times_shifted
        bins_end = [met_times_shifted[i+1] if i+1 < len(met_times_shifted) else (met_times_shifted[i] + dt.timedelta(seconds=interval))
                    for i in range(len(met_times_shifted))]
        j = 0
        for i, t in enumerate(nvspl_times):
            if not overwrite and rows[i].get("WindSpeed"):
                continue
            while j < len(bins_start) and t >= bins_end[j]:
                j += 1
            if j < len(bins_start) and bins_start[j] <= t < bins_end[j]:
                rows[i]["WindSpeed"] = f"{round(met_vals[j], 1):.1f}"
                updated += 1
            else:
                if backfill_before_first and j == 0 and len(met_vals) > 0:
                    rows[i]["WindSpeed"] = f"{round(met_vals[0], 1):.1f}"
                    updated += 1
        return updated

    if method.lower() == "forward":
        latest_val: Optional[float] = None
        j = 0
        for i, t in enumerate(nvspl_times):
            if not overwrite and rows[i].get("WindSpeed"):
                continue
            while j < len(met_times_shifted) and met_times_shifted[j] <= t:
                latest_val = met_vals[j]
                j += 1
            if latest_val is not None:
                rows[i]["WindSpeed"] = f"{round(latest_val, 1):.1f}"
                updated += 1
        return updated

    # nearest
    mt = met_times_shifted
    for i, t in enumerate(nvspl_times):
        if not overwrite and rows[i].get("WindSpeed"):
            continue
        pos = bisect.bisect_left(mt, t)
        candidates: List[Tuple[float, float]] = []
        if pos < len(mt):
            candidates.append((abs((mt[pos] - t).total_seconds()), met_vals[pos]))
        if pos > 0:
            candidates.append((abs((mt[pos-1] - t).total_seconds()), met_vals[pos-1]))
        if candidates:
            best = min(candidates, key=lambda x: x[0])
            if best[0] <= tolerance_sec:
                rows[i]["WindSpeed"] = f"{round(best[1], 1):.1f}"
                updated += 1
    return updated

# ---------- Diagnostics ----------
def debug_met_alignment(rows: List[Dict[str, str]], met_samples: List[Tuple[dt.datetime, float]]) -> None:
    print("---- MET/NVSPL DEBUG ----")
    print(f"Rows (NVSPL): {len(rows)} MET samples: {len(met_samples)}")
    if not rows or not met_samples:
        print("Either NVSPL rows or MET samples are empty. Check encoding/delimiter, indices, and time format.")
        return
    t_rows = [dt.datetime.strptime(r["STime"], "%Y-%m-%d %H:%M:%S.%f") for r in rows]
    print("First 3 NVSPL:", [t_rows[i].strftime("%Y-%m-%d %H:%M:%S") for i in range(min(3, len(t_rows)))])
    print("Last 3 NVSPL:", [t_rows[-i-1].strftime("%Y-%m-%d %H:%M:%S") for i in range(min(3, len(t_rows)))])
    nvspl_min, nvspl_max = min(t_rows), max(t_rows)
    met_min, met_max = met_samples[0][0], met_samples[-1][0]
    print(f"NVSPL range: {nvspl_min} .. {nvspl_max}")
    print(f"MET range: {met_min} .. {met_max}")
    overlaps = not (nvspl_max < met_min or nvspl_min > met_max)
    print(f"Time overlap: {overlaps}")
    if not overlaps:
        print("Hint: MET CSV must cover the same date/hour as the LD files, or adjust LD_TZ/MET_TZ.")
    print("-------------------------")

# ---------- Helper: shift rows by a constant delta ----------
def _shift_rows_to_anchor(rows: List[Dict[str, str]], anchor_dt: dt.datetime) -> None:
    if not rows or anchor_dt is None:
        return
    # Compute delta between first parsed time and anchor
    first_dt = dt.datetime.strptime(rows[0]["STime"], "%Y-%m-%d %H:%M:%S.%f")
    delta = anchor_dt - first_dt
    if delta.total_seconds() == 0:
        return
    for r in rows:
        t = dt.datetime.strptime(r["STime"], "%Y-%m-%d %H:%M:%S.%f")
        t2 = t + delta
        r["STime"] = _fmt_ts(t2)

# ---------- Conversion orchestration ----------
def convert_path(input_path: Path, output_dir: Path, create_site_folders: bool = False, recursive: bool = False) -> None:
    if input_path.is_file():
        files = [input_path]
    else:
        files = sorted(input_path.rglob("*.831")) if recursive else sorted(input_path.glob("*.831"))

    if not files:
        print(f"No .831 files found under: {input_path}")
        return

    # Preload MET (once)
    met_samples: List[Tuple[dt.datetime, float]] = []
    if MERGE_MET and MET_CSV_PATH:
        met_samples = load_met_csv(
            Path(MET_CSV_PATH),
            time_col=MET_TIME_COL,
            wind_col=MET_WIND_COL,
            dt_format=MET_DT_FORMAT,
            # No alignment: we anchor LD via filename and keep MET as local naïve
            src_tz=None,
            dst_tz=None,
            units=WIND_UNITS,
            convert_mph_to_mps=CONVERT_MPH_TO_MPS
        )

    for f in files:
        site = f.stem.split("_")[1] if "_" in f.stem else ""
        out_dir = output_dir / site if create_site_folders and site else output_dir
        print(f"Parsing {f} ({'NEW' if is_ld831_new(f) else 'OLD'}) ...")
        rows = list(parse_ld831(f))

        # --- Anchor timestamps to filename ---
        anchor_dt = _dt_from_filename(f.stem)
        if anchor_dt:
            _shift_rows_to_anchor(rows, anchor_dt)
            print(f"[ANCHOR] First NVSPL time aligned to filename: {anchor_dt}")
        else:
            print("[ANCHOR] Filename did not match expected pattern; skipping anchor.")

        # Diagnostics before merge
        debug_met_alignment(rows, met_samples)

        merged_count = 0
        if MERGE_MET and met_samples:
            merged_count = merge_wind_into_rows(
                rows,
                met_samples=met_samples,
                method=FILL_METHOD,
                tolerance_sec=NEAREST_TOLERANCE_SEC,
                overwrite=OVERWRITE_EXISTING_WIND,
                sample_stamp=MET_SAMPLE_STAMP,
                backfill_before_first=BACKFILL_BEFORE_FIRST
            )
        print(f"Merged WindSpeed into {merged_count} of {len(rows)} rows (method={FILL_METHOD}).")
        if merged_count == 0 and rows and met_samples:
            first_row_ts = dt.datetime.strptime(rows[0]["STime"], "%Y-%m-%d %H:%M:%S.%f")
            if FILL_METHOD == "forward" and first_row_ts < met_samples[0][0]:
                print("Note: forward-fill leaves seconds before the first MET timestamp blank.")
            elif FILL_METHOD == "nearest":
                print("Tip: increase NEAREST_TOLERANCE_SEC if MET intervals are coarse.")

        buckets = bucket_by_hour(rows)
        for (site_id, hour_start), lst in sorted(buckets.items(), key=lambda kv: kv[1][0]["STime"]):
            p = write_nvspl_hour(out_dir, site_id, hour_start, lst)
            print(f" wrote {p}")

# ---------- Run ----------
if __name__ == "__main__":
    convert_path(Path(INPUT_PATH), Path(OUTPUT_PATH),
                 create_site_folders=CREATE_SITE_FOLDERS,
                 recursive=RECURSIVE)
