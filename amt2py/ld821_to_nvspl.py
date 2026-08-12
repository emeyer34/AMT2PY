# -*- coding: utf-8 -*-
"""
LD821 Time History CSV -> NVSPL (C# parity) + MET merge with Tkinter GUI.
"""

import os, csv, math, re, io, bisect, threading
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from amt2py.shared_gui_components import (
    ToolTip,
    WorkerGuiMixin,
    add_progress_bar,
    add_scrolled_text,
    create_file_logger,
    close_logger,
)
from amt2py.schemas.feathermc_met import (
    FEATHERMC_COMBINED_TIMESTAMP,
    FEATHERMC_WIND_GUST,
    fuzzy_met_column_indices,
    feathermc_met_runtime_indices,
    infer_feathermc_met_gui_indices,
    is_feathermc_combined_header,
)
from amt2py.schemas.ld821_spl import (
    LD821_COMBINED_BASENAME,
    LD821_HEADER_MARKER,
    LD821_TIMESTAMP_FMT,
    infer_spl_gui_defaults,
    validate_ld821_header,
)
from amt2py.schemas.utils import header_columns, normalize_gui_path

# ==============================================================================
# 1. CORE PROCESSING LOGIC (Preserved & Adapted for GUI Integration)
# ==============================================================================

NVSPL_HEADER = [
    "SiteID","STime",
    "H12p5","H15p8","H20","H25","H31p5","H40","H50","H63","H80","H100",
    "H125","H160","H200","H250","H315","H400","H500","H630","H800","H1000","H1250",
    "H1600","H2000","H2500","H3150","H4000","H5000","H6300","H8000","H10000","H12500",
    "H16000","H20000",
    "dbA","dbC","dbF",
    "Voltage","WindSpeed","WindDir","TempIns","TempOut","Humidity",
    "INVID","INSID","GChar1","GChar2","GChar3",
    "AdjustmentsApplied","CalibrationAdjustment","GPSTimeAdjustment","GainAdjustment","Status"
]

AWT = [
    -63.4, -56.7, -50.5, -44.7, -39.4, -34.6, -30.2, -26.2, -22.5, -19.1,
    -16.1, -13.4, -10.9,  -8.6,  -6.6,  -4.8,  -3.2,  -1.9,  -0.8,   0.0,
      0.6,   1.0,   1.2,   1.3,   1.2,   1.0,   0.5,  -0.1,  -1.1,  -2.5,
     -4.3,  -6.6,  -9.3
]

COMPASS_TO_DEG = {
    "N":0.0,"NNE":22.5,"NE":45.0,"ENE":67.5,"E":90.0,"ESE":112.5,"SE":135.0,"SSE":157.5,
    "S":180.0,"SSW":202.5,"SW":225.0,"WSW":247.5,"W":270.0,"WNW":292.5,"NW":315.0,"NNW":337.5
}

# Defaults when header auto-fill does not apply (non-combined MET).
NVSPL_MET_GUI_DEFAULTS = {
    "MET_TIMESTAMP_IDX": "",
    "MET_WINDSPD_IDX": "3",
    "MET_WINDDIR_IDX": "None",
    "MET_EXTERNTEMP_IDX": "None",
    "MET_SAMPLE_STAMP": "start",    # 10 s Feather MC sample intervals
    "FILL_METHOD": "bin",
    "NEAREST_TOLERANCE_SEC": "2",
    "BACKFILL_BEFORE_FIRST": "False",
    "MET_SPEED_UNITS": "mps",
    "CONVERT_MPH_TO_MPS": "False",
    "MET_INVALID_SPEED": "39.9",    # common invalid/sentinel reading on field loggers
}

_RE_MET_MDY = re.compile(
    r'(?P<mdy>\b\d{1,2}/\d{1,2}/\d{2,4})\s+'
    r'(?P<hms>\d{1,2}:\d{2}(?::\d{2})?)\s*'
    r'(?P<ampm>\bAM\b|\bPM\b|\bam\b|\bpm\b)?'
)
_RE_MET_ISO = re.compile(
    r'(?P<iso>\b\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+\-]\d{2}:\d{2})?)'
)

def ensure_dir(path: str):
    if path and not os.path.exists(path):
        os.makedirs(path)

def generate_filename(out_dir: str, site: str, dt_hour: datetime) -> str:
    return os.path.join(out_dir, f"NVSPL_{site}_{dt_hour.strftime('%Y_%m_%d_%H')}.txt")

def create_blank_hour(site: str, hour_start: datetime):
    rows = []
    for sec in range(3600):
        t = hour_start + timedelta(seconds=sec)
        stime = t.strftime("%Y-%m-%d %H:%M:%S") + ".000"
        row = [site, stime] + [""] * (len(NVSPL_HEADER) - 2)
        rows.append(row)
    return rows

def write_hour_file(out_dir: str, site: str, hour_start: datetime, filled_rows):
    ensure_dir(out_dir)
    path = generate_filename(out_dir, site, hour_start)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(NVSPL_HEADER)
        for r in filled_rows:
            w.writerow(r)
    return path

def parse_timestamp_ld821(ts_str: str) -> datetime:
    return datetime.strptime(ts_str.strip(), LD821_TIMESTAMP_FMT)

def compute_dba_from_bands(bands_33):
    try:
        s = 0.0
        for i in range(32):
            s += 10.0 ** ((float(bands_33[i]) + float(AWT[i])) / 10.0)
        return f"{10.0 * math.log10(s):.1f}"
    except Exception:
        return ""

def parse_ld821_to_day_records(site: str, src_csv: str):
    with open(src_csv, "r", encoding="utf-8", newline="") as f:
        hdr = None
        for line in f:
            if LD821_HEADER_MARKER in line:
                hdr = next(csv.reader([line]))
                break
        if not hdr:
            raise RuntimeError(f"LD821 header line containing {LD821_HEADER_MARKER!r} not found.")

        col = validate_ld821_header(hdr)
        sdateLoc = col["sdate_idx"]
        dbaLoc = col["dba_idx"] if col["dba_idx"] is not None else -100
        dbzLoc = col["dbz_idx"] if col["dbz_idx"] is not None else -100
        dbcLoc = col["dbc_idx"] if col["dbc_idx"] is not None else -100
        powerLoc = col["power_idx"] if col["power_idx"] is not None else -100
        h12p5Loc = col["h12p5_idx"]
        ovrLoc = col["ovr_idx"] if col["ovr_idx"] is not None else -100

        out_per_day = {}
        current_day = None

        for row in csv.reader(f):
            if not row or len(row) <= h12p5Loc + 32:
                continue

            temp_ts = parse_timestamp_ld821(row[sdateLoc])
            row_day = temp_ts.strftime("%Y-%m-%d")
            if row_day != current_day:
                current_day = row_day
                out_per_day.setdefault(current_day, [])

            bands_33 = [row[h12p5Loc + i].strip() for i in range(33)]

            valid_line = True
            try:
                for v in bands_33:
                    if float(v) < -50.0:
                        valid_line = False
                        break
            except Exception:
                valid_line = False
            if not valid_line:
                continue

            dbA = row[dbaLoc].strip() if dbaLoc > 0 else ""
            dbF = row[dbzLoc].strip() if dbzLoc > 0 else ""
            dbC = row[dbcLoc].strip() if dbcLoc > 0 else ""
            volt = row[powerLoc].strip() if powerLoc > 0 else ""
            status = ""
            if ovrLoc > 0 and row[ovrLoc].strip() != "":
                status = "9911"

            if (dbaLoc < 0) or (dbA == ""):
                dbA = compute_dba_from_bands(bands_33)

            record = [site, temp_ts] + bands_33 + [dbA, dbC, dbF, volt] + [""] * 13 + [status]

            if len(record) != len(NVSPL_HEADER):
                record = (record + [""] * (len(NVSPL_HEADER) - len(record)))[:len(NVSPL_HEADER)]

            out_per_day[current_day].append(record)

    return out_per_day

def parse_daily_file_to_hours(site: str, day_records: list):
    if not day_records:
        return []

    hours = {}
    for rec in day_records:
        dt_val = rec[1] if isinstance(rec[1], datetime) else datetime.strptime(rec[1], "%Y-%m-%d %H:%M:%S.000")
        hour_start = dt_val.replace(minute=0, second=0, microsecond=0)
        key = hour_start.strftime("%Y-%m-%d %H")
        if key not in hours:
            hours[key] = {"start": hour_start, "rows": create_blank_hour(site, hour_start)}
        sec_tot = dt_val.minute * 60 + dt_val.second
        hours[key]["rows"][sec_tot][2:] = rec[2:]

    return [hours[k] for k in sorted(hours.keys())]

def read_csv_rows_by_index(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        r = csv.reader(f)
        return [row for row in r]

def try_parse_dt_common(s: str):
    s = (s or "").strip()
    if not s: return None
    def _normalize_no_colon(ts: str):
        parts = ts.split(" ", 1)
        if len(parts) == 2 and len(parts[1]) == 6 and parts[1].isdigit():
            return parts[0] + " " + f"{parts[1][0:2]}:{parts[1][2:4]}:{parts[1][4:6]}"
        return ts
    s_norm = _normalize_no_colon(s)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%d-%b-%y %H:%M:%S"):
        try: return datetime.strptime(s_norm, fmt).replace(microsecond=0)
        except Exception: pass
    return None

def try_parse_dt_from_two_cols(date_s: str, time_s: str):
    date_s, time_s = (date_s or "").strip(), (time_s or "").strip()
    if not date_s or not time_s: return None
    t_norm = f"{time_s[0:2]}:{time_s[2:4]}:{time_s[4:6]}" if len(time_s) == 6 and time_s.isdigit() else time_s
    candidate = f"{date_s} {t_norm}"
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%d-%b-%y %H:%M:%S"):
        try: return datetime.strptime(candidate, fmt).replace(microsecond=0)
        except Exception: pass
    return None

def infer_met_gui_indices(header_row):
    """Fill NVSPL MET index fields from CSV header."""
    if is_feathermc_combined_header(header_row):
        inferred = infer_feathermc_met_gui_indices(header_row)
        return {
            key: inferred.get(key) or NVSPL_MET_GUI_DEFAULTS.get(key, "")
            for key in (
                "MET_TIMESTAMP_IDX",
                "MET_WINDSPD_IDX",
                "MET_WINDDIR_IDX",
                "MET_EXTERNTEMP_IDX",
            )
        }

    cols = header_columns(header_row)
    is_cv3_export = bool(cols) and cols[0] == "Plot Title"
    fuzzy = fuzzy_met_column_indices(header_row, infer_wind=not is_cv3_export)
    result = dict(NVSPL_MET_GUI_DEFAULTS)

    if fuzzy["ts_idx"] is not None:
        result["MET_TIMESTAMP_IDX"] = str(fuzzy["ts_idx"])
    elif is_cv3_export and "Timestamp" in cols:
        result["MET_TIMESTAMP_IDX"] = str(cols.index("Timestamp"))

    if fuzzy["spd_idx"] is not None:
        result["MET_WINDSPD_IDX"] = str(fuzzy["spd_idx"])
    if fuzzy["dir_idx"] is not None:
        result["MET_WINDDIR_IDX"] = str(fuzzy["dir_idx"])
    if fuzzy["tmp_idx"] is not None:
        result["MET_EXTERNTEMP_IDX"] = str(fuzzy["tmp_idx"])

    return {
        k: result[k]
        for k in (
            "MET_TIMESTAMP_IDX",
            "MET_WINDSPD_IDX",
            "MET_WINDDIR_IDX",
            "MET_EXTERNTEMP_IDX",
        )
    }

def auto_detect_met_indices(rows, user_ts_idx, user_spd_idx, user_dir_idx, user_tmp_idx):
    header = rows[0] if rows else []
    hdr_tokens = [str(x or "").strip().lower() for x in header]
    has_header = any(any(c.isalpha() for c in (cell or "")) for cell in header)

    schema = {
        "ts_idx": user_ts_idx, "date_idx": None, "time_idx": None,
        "spd_idx": user_spd_idx, "dir_idx": user_dir_idx, "tmp_idx": user_tmp_idx,
        "source": "GENERIC_CSV"
    }

    is_feathermc_combined = is_feathermc_combined_header(header)
    is_mx1105 = any("adc1" in h or "adc2" in h for h in hdr_tokens)
    has_dir_hdr = any("dir" in h for h in hdr_tokens)
    has_spd_hdr = any("spd" in h or "speed" in h or "gust" in h for h in hdr_tokens)

    if is_feathermc_combined:
        schema["source"] = "FEATHERMC_COMBINED"
        exact = feathermc_met_runtime_indices(header)
        if schema["ts_idx"] is None:
            schema["ts_idx"] = exact["ts_idx"]
        if schema["spd_idx"] is None:
            schema["spd_idx"] = exact["spd_idx"]
        if schema["dir_idx"] is None:
            schema["dir_idx"] = exact["dir_idx"]
        if schema["tmp_idx"] is None:
            schema["tmp_idx"] = exact["tmp_idx"]

    elif is_mx1105:
        schema["source"] = "MX1105_CSV"
        if schema["tmp_idx"] is None:
            for i, h in enumerate(hdr_tokens):
                if "adc1" in h: schema["tmp_idx"] = i; break
        if schema["spd_idx"] is None:
            for i, h in enumerate(hdr_tokens):
                if "gust" in h or "spd" in h or "speed" in h: schema["spd_idx"] = i; break

    elif has_dir_hdr and has_spd_hdr:
        schema["source"] = "CV3_CSV"
        if schema["dir_idx"] is None:
            for i, h in enumerate(hdr_tokens):
                if "dir" in h: schema["dir_idx"] = i; break
        if schema["spd_idx"] is None:
            for i, h in enumerate(hdr_tokens):
                if "gust" in h or "spd" in h or "speed" in h: schema["spd_idx"] = i; break
        if schema["tmp_idx"] is None:
            for i, h in enumerate(hdr_tokens):
                if "temp" in h or "ext" in h: schema["tmp_idx"] = i; break

    if schema["ts_idx"] is None:
        start = 1 if has_header else 0
        sample_n = min(len(rows) - start, 500)
        if sample_n > 0:
            best_ts_idx, best_hits = None, -1
            row0_len = len(rows[start]) if start < len(rows) else 0
            for c in range(row0_len):
                hits = sum(1 for i in range(start, start + sample_n) if len(rows[i]) > c and try_parse_dt_common(rows[i][c]))
                if hits > best_hits: best_ts_idx, best_hits = c, hits
            if best_hits < max(5, sample_n // 20):
                best_pair = (None, None, -1)
                for di in range(row0_len):
                    for ti in range(row0_len):
                        if di == ti: continue
                        hits = sum(1 for i in range(start, start + sample_n) if len(rows[i]) > max(di, ti) and try_parse_dt_from_two_cols(rows[i][di], rows[i][ti]))
                        if hits > best_pair[2]: best_pair = (di, ti, hits)
                if best_pair[2] > best_hits: schema["date_idx"], schema["time_idx"] = best_pair[0], best_pair[1]
                else: schema["ts_idx"] = best_ts_idx
            else: schema["ts_idx"] = best_ts_idx

    if schema["spd_idx"] is None and len(rows) > 1:
        start = 1 if has_header else 0
        sample_n = min(len(rows) - start, 300)
        max_cols = max((len(r) for r in rows[start:start + sample_n]), default=0)
        best_idx, best_nums = None, -1
        for c in range(max_cols):
            nums = 0
            for r in rows[start:start + sample_n]:
                if len(r) > c:
                    try: float(r[c]); nums += 1
                    except Exception: pass
            if nums > best_nums: best_idx, best_nums = c, nums
        schema["spd_idx"] = best_idx

    return schema

def _sniff_encoding(path):
    try:
        with open(path, "rb") as fb:
            head = fb.read(4)
            if head.startswith(b"\xff\xfe"): return "utf-16-le"
            if head.startswith(b"\xfe\xff"): return "utf-16-be"
            if head.startswith(b"\xef\xbb\xbf"): return "utf-8-sig"
    except Exception: pass
    return "utf-8"

def _sniff_delimiter(sample_text):
    try: return csv.Sniffer().sniff(sample_text, delimiters="\t,;").delimiter
    except Exception: return ("\t" if "\t" in sample_text else ("," if "," in sample_text else ";"))

def _extract_dt_string(s: str):
    if not s: return None
    s = s.replace("\ufeff", "").replace("\xa0", " ").strip().strip('"').strip("'")
    m = _RE_MET_MDY.search(s)
    if m:
        dt_str = f"{m.group('mdy')} {m.group('hms')}"
        if m.group('ampm'): dt_str += f" {m.group('ampm').upper()}"
        return dt_str
    m = _RE_MET_ISO.search(s)
    return m.group('iso') if m else None

def _parse_dt_flex(s: str):
    s = (s or "").strip()
    if not s: return None
    core = _extract_dt_string(s) or s
    for cand in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %I:%M %p",
                 "%m/%d/%y %H:%M:%S", "%m/%d/%y %H:%M", "%m/%d/%y %I:%M:%S %p", "%m/%d/%y %I:%M %p",
                 "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try: return datetime.strptime(core, cand).replace(microsecond=0)
        except Exception: pass
    return None

def _infer_interval_seconds(times: list[datetime]) -> int:
    if len(times) < 2: return 1
    deltas = sorted([d for d in [(times[i] - times[i-1]).total_seconds() for i in range(1, len(times))] if d > 0])
    if not deltas: return 1
    median = deltas[len(deltas)//2]
    for cand in (1,2,5,10,15,20,30,60,120,300):
        if abs(median - cand) <= 0.6: return cand
    return int(round(median))

def _shift_times_for_stamp(times: list[datetime], interval_sec: int, stamp: str) -> list[datetime]:
    s = (stamp or "start").lower()
    if interval_sec <= 0 or s == "start": return times
    shift = interval_sec/2.0 if s == "center" else (interval_sec if s == "end" else 0)
    return times if shift == 0 else [t - timedelta(seconds=shift) for t in times]

def _norm_speed(val: str, invalid_set: set) -> str:
    s = (str(val) or "").strip()
    if s in invalid_set: return ""
    try: return f"{float(s):.1f}"
    except Exception: return ""

def _norm_dir(val: str) -> str:
    s = (str(val) or "").strip().upper()
    if s in COMPASS_TO_DEG: return f"{COMPASS_TO_DEG[s]:.1f}"
    try: return f"{float(s):.1f}"
    except Exception: return ""

def _norm_temp(val: str) -> str:
    try: return f"{float(str(val).strip()):.1f}"
    except Exception: return ""

def _read_met_csv_header(csv_path: str):
    """Read only the first non-empty CSV row (for GUI defaults — not full file load)."""
    enc = _sniff_encoding(csv_path)
    try:
        with open(csv_path, "rb") as fb:
            sample_text = fb.read(65536).decode(enc, errors="replace")
    except Exception:
        sample_text = ""
    delim = _sniff_delimiter(sample_text)

    try:
        with open(csv_path, "r", encoding=enc, newline="") as f:
            for row in csv.reader(f, delimiter=delim):
                if row and any(str(c).strip() for c in row):
                    return row
    except Exception:
        pass
    return []

def _read_met_data_rows(csv_path: str):
    enc = _sniff_encoding(csv_path)
    sample_bytes = b""
    try:
        with open(csv_path, "rb") as fb:
            sample_bytes = fb.read(65536)
    except Exception:
        pass
    sample_text = sample_bytes.decode(enc, errors="replace")
    delim = _sniff_delimiter(sample_text)

    rows = []
    try:
        with open(csv_path, "r", encoding=enc, newline="") as f:
            for row in csv.reader(f, delimiter=delim):
                if not row:
                    continue
                rows.append(row)
    except Exception:
        with open(csv_path, "r", encoding=enc, errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                for cand in ("\t", ",", ";"):
                    if cand in line:
                        try:
                            row = next(csv.reader(io.StringIO(line), delimiter=cand))
                            if row:
                                rows.append(row)
                        except Exception:
                            pass
                        break
    return rows

def _met_rows_for_schema(rows):
    data_rows = []
    for row in rows:
        if not row:
            continue
        first = (row[0] or "").strip()
        if first.startswith("#") or "Date" in first or "Time" in first or "GMT" in first or "UTC" in first:
            continue
        data_rows.append(row)
    return data_rows if data_rows else rows

def _parse_met_rows_to_samples(rows, schema: dict, units: str, convert_mph_to_mps: bool, invalid_set: set):
    samples = []
    use_single = schema.get("ts_idx") is not None
    ts_i = schema.get("ts_idx")
    di, ti = schema.get("date_idx"), schema.get("time_idx")
    spd_i, dir_i, tmp_i = schema.get("spd_idx"), schema.get("dir_idx"), schema.get("tmp_idx")

    for row in rows:
        dt_val = None
        if use_single and ts_i is not None and len(row) > ts_i:
            dt_val = _parse_dt_flex(row[ts_i]) or try_parse_dt_common(row[ts_i])
        elif di is not None and ti is not None and len(row) > max(di, ti):
            dt_val = try_parse_dt_from_two_cols(row[di], row[ti])
        if not dt_val:
            continue

        spd = ""
        if spd_i is not None and len(row) > spd_i:
            spd_raw = row[spd_i]
            try:
                v = float(str(spd_raw).strip())
                if units.lower() == "mph" and convert_mph_to_mps:
                    v *= 0.44704
                spd = f"{v:.1f}"
            except Exception:
                spd = _norm_speed(spd_raw, invalid_set)

        drr = _norm_dir(row[dir_i]) if dir_i is not None and len(row) > dir_i else ""
        tmp = _norm_temp(row[tmp_i]) if tmp_i is not None and len(row) > tmp_i else ""

        samples.append((dt_val.replace(microsecond=0), {"spd": spd, "dir": drr, "tmp": tmp}))

    samples.sort(key=lambda x: x[0])
    return samples

def load_met_samples(config, log_func):
    if not config["MERGE_MET"]:
        return None

    all_rows = _read_met_data_rows(config["MET_CSV_PATH"])
    schema = auto_detect_met_indices(
        all_rows,
        config["MET_TIMESTAMP_IDX"],
        config["MET_WINDSPD_IDX"],
        config["MET_WINDDIR_IDX"],
        config["MET_EXTERNTEMP_IDX"],
    )
    log_func(f"[MET] Source={schema['source']}, TS_idx={schema['ts_idx']}, Spd_idx={schema['spd_idx']}")

    data_rows = _met_rows_for_schema(all_rows)
    samples = _parse_met_rows_to_samples(
        data_rows,
        schema=schema,
        units=config["MET_SPEED_UNITS"],
        convert_mph_to_mps=config["CONVERT_MPH_TO_MPS"],
        invalid_set=config["MET_INVALID_SPEED"],
    )
    if samples:
        log_func(f"[MET] Loaded {len(samples)} samples.")
    else:
        log_func("[MET] Parsed 0 samples; verify CSV structure.")
    return samples

def _prepare_met_bin_context(samples, stamp: str):
    times = [t for (t, _) in samples]
    vals = [v for (_, v) in samples]
    interval = _infer_interval_seconds(times)
    times_shifted = _shift_times_for_stamp(times, interval, stamp)
    bins_start = times_shifted
    bins_end = [
        times_shifted[i + 1] if i + 1 < len(times_shifted)
        else (times_shifted[i] + timedelta(seconds=interval))
        for i in range(len(times_shifted))
    ]
    return {"bins_start": bins_start, "bins_end": bins_end, "vals": vals}

def _overlay_met_bin(rows_3600: list, hour_start: datetime, ctx: dict, backfill_before_first: bool, j: int = 0):
    bins_start, bins_end, vals = ctx["bins_start"], ctx["bins_end"], ctx["vals"]
    if not bins_start:
        return 0, j

    updated = 0
    for sec in range(3600):
        t = hour_start + timedelta(seconds=sec)
        while j < len(bins_start) and t >= bins_end[j]:
            j += 1
        if j < len(bins_start) and bins_start[j] <= t < bins_end[j]:
            v = vals[j]
            if v.get("spd"): rows_3600[sec][39] = v["spd"]
            if v.get("dir"): rows_3600[sec][40] = v["dir"]
            if v.get("tmp"): rows_3600[sec][42] = v["tmp"]
            updated += 1
        elif backfill_before_first and j == 0 and len(vals) > 0:
            v = vals[0]
            if v.get("spd"): rows_3600[sec][39] = v["spd"]
            if v.get("dir"): rows_3600[sec][40] = v["dir"]
            if v.get("tmp"): rows_3600[sec][42] = v["tmp"]
            updated += 1
    return updated, j

def _overlay_met_forward(rows_3600: list, hour_start: datetime, times: list, vals: list, j: int = 0, latest=None):
    if not times:
        return 0, j, latest

    updated = 0
    for sec in range(3600):
        t = hour_start + timedelta(seconds=sec)
        while j < len(times) and times[j] <= t:
            latest = vals[j]
            j += 1
        if latest:
            if latest.get("spd"): rows_3600[sec][39] = latest["spd"]
            if latest.get("dir"): rows_3600[sec][40] = latest["dir"]
            if latest.get("tmp"): rows_3600[sec][42] = latest["tmp"]
            updated += 1
    return updated, j, latest

def _overlay_met_nearest(rows_3600: list, hour_start: datetime, mt: list, mv: list, tol_sec: int):
    if not mt:
        return 0

    updated = 0
    for sec in range(3600):
        t = hour_start + timedelta(seconds=sec)
        pos = bisect.bisect_left(mt, t)
        candidates = []
        if pos < len(mt):
            candidates.append((abs((mt[pos] - t).total_seconds()), mv[pos]))
        if pos > 0:
            candidates.append((abs((mt[pos - 1] - t).total_seconds()), mv[pos - 1]))
        if candidates:
            best = min(candidates, key=lambda x: x[0])
            if best[0] <= tol_sec:
                v = best[1]
                if v.get("spd"): rows_3600[sec][39] = v["spd"]
                if v.get("dir"): rows_3600[sec][40] = v["dir"]
                if v.get("tmp"): rows_3600[sec][42] = v["tmp"]
                updated += 1
    return updated

def merge_met_for_day(hour_bundles, config, log_func, met_samples=None):
    if not config["MERGE_MET"]:
        return hour_bundles

    samples = met_samples
    if samples is None:
        samples = load_met_samples(config, log_func)
    if not samples:
        log_func("[MET] No valid samples parsed.")
        return hour_bundles

    method = config["FILL_METHOD"].lower()
    total_updates = 0

    if method == "bin":
        ctx = _prepare_met_bin_context(samples, config["MET_SAMPLE_STAMP"])
        j = 0
        for b in hour_bundles:
            updated, j = _overlay_met_bin(
                b["rows"], b["start"], ctx, config["BACKFILL_BEFORE_FIRST"], j
            )
            total_updates += updated
        log_func(f"[MERGE] bin-fill: updated={total_updates} secs across {len(hour_bundles)} hours")
    elif method == "forward":
        times = [t for (t, _) in samples]
        vals = [v for (_, v) in samples]
        j, latest = 0, None
        for b in hour_bundles:
            updated, j, latest = _overlay_met_forward(b["rows"], b["start"], times, vals, j, latest)
            total_updates += updated
        log_func(f"[MERGE] forward-fill: updated={total_updates} secs across {len(hour_bundles)} hours")
    else:
        mt = [t for (t, _) in samples]
        mv = [v for (_, v) in samples]
        for b in hour_bundles:
            total_updates += _overlay_met_nearest(
                b["rows"], b["start"], mt, mv, config["NEAREST_TOLERANCE_SEC"]
            )
        log_func(f"[MERGE] nearest-fill: updated={total_updates} secs across {len(hour_bundles)} hours")

    log_func(f"[MERGE] Total updated NVSPL records: {total_updates}")
    return hour_bundles

# ==============================================================================
# 2. GUI INTERFACE (Tkinter)
# ==============================================================================

class AppGUI(WorkerGuiMixin, tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LD821 CSV to NVSPL Converter")
        self.geometry("780x820")
        self.minsize(640, 600)
        self.resizable(True, True)

        self.vars = {}
        self.init_worker_state()
        self._setup_ui()

    def _setup_ui(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        run_bar = ttk.Frame(main_frame)
        run_bar.pack(side=tk.BOTTOM, fill=tk.X, pady=(4, 0))
        self.btn_run = ttk.Button(run_bar, text="Run Conversion Process", command=self.start_processing)
        self.btn_run.pack(fill=tk.X)
        add_progress_bar(run_bar, self)

        grp_log = ttk.LabelFrame(main_frame, text=" Process Output Log ", padding="5")
        grp_log.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True, pady=5)
        self.txt_log = add_scrolled_text(grp_log, height=8, expand=True)

        content = ttk.Frame(main_frame)
        content.pack(fill=tk.BOTH, expand=True)

        # File and Main Settings Frame
        grp_paths = ttk.LabelFrame(content, text=" File Paths & Site Info ", padding="10")
        grp_paths.pack(fill=tk.X, pady=5)

        self._create_path_row(grp_paths, 0, "INPUT_CSV", "Input SPL CSV:", f"Combined {{site}}_{LD821_COMBINED_BASENAME} — SITE_ID autofill on browse", is_file=True)
        self._create_path_row(grp_paths, 1, "OUTPUT_DIR", "Output Folder:", "Navigate to NVSPL folder", is_file=False)
        self._create_entry_row(grp_paths, 2, "SITE_ID", "Site ID:", "Typically park code and three digit number (ex. CARE001)")

        # MET Settings Frame
        grp_met = ttk.LabelFrame(content, text=" MET (Wind) Data Merge Settings ", padding="10")
        grp_met.pack(fill=tk.X, pady=5)

        self._create_combo_row(grp_met, 0, "MERGE_MET", "Merge MET Data:", ["True", "False"], "Do you want to merge met and spl data?")
        self._create_path_row(grp_met, 1, "MET_CSV_PATH", "MET Data CSV:", "Navigate to combined wind dataset", is_file=True)
        self._create_entry_row(grp_met, 2, "MET_TIMESTAMP_IDX", "Timestamp Col Index:", f"auto: exact match on {FEATHERMC_COMBINED_TIMESTAMP!r}")
        self._create_entry_row(grp_met, 3, "MET_WINDSPD_IDX", "Wind Speed Col Index:", f"auto: exact match on {FEATHERMC_WIND_GUST[0]!r} (or {FEATHERMC_WIND_GUST[1]!r})")
        self._create_entry_row(grp_met, 4, "MET_WINDDIR_IDX", "Wind Dir Col Index:", "optional; auto-filled from header when present")
        self._create_entry_row(grp_met, 5, "MET_EXTERNTEMP_IDX", "Temp Col Index:", "external temp column index (optional)")

        # Strategy and Units Settings Frame
        grp_strat = ttk.LabelFrame(content, text=" Alignment & Units ", padding="10")
        grp_strat.pack(fill=tk.X, pady=5)

        self._create_combo_row(grp_strat, 0, "MET_SAMPLE_STAMP", "Sample Stamp:", ["start", "center", "end"], "Feather MC 10 s samples: use start")
        self._create_combo_row(grp_strat, 1, "FILL_METHOD", "Fill Method:", ["bin", "forward", "nearest"], "bin repeats each MET sample across its interval")
        self._create_entry_row(grp_strat, 2, "NEAREST_TOLERANCE_SEC", "Nearest Tolerance (s):", "")
        self._create_combo_row(grp_strat, 3, "BACKFILL_BEFORE_FIRST", "Backfill Before First:", ["False", "True"], "bin/forward: fill seconds before first MET sample?")
        self._create_combo_row(grp_strat, 4, "MET_SPEED_UNITS", "Wind Speed Units:", ["mps", "mph"], "What are the units for wind speed")
        self._create_combo_row(grp_strat, 5, "CONVERT_MPH_TO_MPS", "Convert MPH to MPS:", ["False", "True"], "")
        self._create_entry_row(grp_strat, 6, "MET_INVALID_SPEED", "Invalid Speed Entries:", "comma-separated sentinels to blank (e.g. 39.9)")

        # Default Value Loading
        self._load_defaults()

    def _create_entry_row(self, parent, row, key, label_text, hint):
        lbl = ttk.Label(parent, text=label_text, width=22, anchor="w")
        lbl.grid(row=row, column=0, sticky="w", pady=2)
        var = tk.StringVar()
        ent = ttk.Entry(parent, textvariable=var)
        ent.grid(row=row, column=1, sticky="ew", padx=5, pady=2)
        parent.columnconfigure(1, weight=1)
        self.vars[key] = var
        if hint:
            ToolTip(ent, hint)
            ToolTip(lbl, hint)

    def _create_combo_row(self, parent, row, key, label_text, values, hint):
        lbl = ttk.Label(parent, text=label_text, width=22, anchor="w")
        lbl.grid(row=row, column=0, sticky="w", pady=2)
        var = tk.StringVar()
        cmb = ttk.Combobox(parent, textvariable=var, values=values, state="readonly")
        cmb.grid(row=row, column=1, sticky="ew", padx=5, pady=2)
        parent.columnconfigure(1, weight=1)
        self.vars[key] = var
        if hint:
            ToolTip(cmb, hint)
            ToolTip(lbl, hint)

    def _create_path_row(self, parent, row, key, label_text, hint, is_file=True):
        lbl = ttk.Label(parent, text=label_text, width=22, anchor="w")
        lbl.grid(row=row, column=0, sticky="w", pady=2)
        var = tk.StringVar()
        ent = ttk.Entry(parent, textvariable=var)
        ent.grid(row=row, column=1, sticky="ew", padx=5, pady=2)

        def browse():
            if is_file:
                res = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")])
            else:
                res = filedialog.askdirectory()
            if res:
                var.set(normalize_gui_path(res))
                if key == "INPUT_CSV":
                    self._apply_spl_csv_defaults(res)
                elif key == "MET_CSV_PATH":
                    self._apply_met_csv_defaults(res)

        btn = ttk.Button(parent, text="Browse...", width=10, command=browse)
        btn.grid(row=row, column=2, padx=2, pady=2)

        parent.columnconfigure(1, weight=1)
        self.vars[key] = var
        if hint:
            ToolTip(ent, hint)
            ToolTip(lbl, hint)

    def _load_defaults(self):
        defaults = {
            "INPUT_CSV": "",
            "OUTPUT_DIR": "",
            "SITE_ID": "",
            "MERGE_MET": "False",
            "MET_CSV_PATH": "",
            **NVSPL_MET_GUI_DEFAULTS,
        }
        for k, v in defaults.items():
            if k in self.vars:
                self.vars[k].set(v)

    def _apply_spl_csv_defaults(self, csv_path):
        """Fill SITE_ID (and OUTPUT_DIR if empty) from ld821_combine filename."""
        try:
            inferred = infer_spl_gui_defaults(csv_path)
            if inferred.get("SITE_ID") and "SITE_ID" in self.vars:
                self.vars["SITE_ID"].set(inferred["SITE_ID"])
            if inferred.get("OUTPUT_DIR") and "OUTPUT_DIR" in self.vars:
                if not self.vars["OUTPUT_DIR"].get().strip():
                    self.vars["OUTPUT_DIR"].set(inferred["OUTPUT_DIR"])
        except Exception:
            pass

    def _apply_met_csv_defaults(self, csv_path):
        """Fill MET column indices from FeatherMC combined CSV header."""
        try:
            header = _read_met_csv_header(csv_path)
            if not header:
                return
            inferred = infer_met_gui_indices(header)
            for key, value in inferred.items():
                if key in self.vars and value:
                    self.vars[key].set(value)
            self.vars["MERGE_MET"].set("True")
        except Exception:
            pass

    def _append_log(self, message):
        self.txt_log.insert(tk.END, message + "\n")
        self.txt_log.see(tk.END)

    def log(self, message):
        self._on_ui(self._append_log, str(message))

    def _set_busy(self, busy):
        self._set_run_busy(busy, idle_text="Run Conversion Process")

    def parse_optional_idx(self, val_str):
        val_str = str(val_str).strip()
        if not val_str or val_str.lower() == "none":
            return None
        return int(val_str)

    def start_processing(self):
        if self._worker_running:
            return

        self.txt_log.delete("1.0", tk.END)
        try:
            config = {
                "INPUT_CSV": normalize_gui_path(self.vars["INPUT_CSV"].get()),
                "OUTPUT_DIR": normalize_gui_path(self.vars["OUTPUT_DIR"].get()),
                "SITE_ID": self.vars["SITE_ID"].get(),
                "MERGE_MET": self.vars["MERGE_MET"].get() == "True",
                "MET_CSV_PATH": normalize_gui_path(self.vars["MET_CSV_PATH"].get()),
                "MET_TIMESTAMP_IDX": self.parse_optional_idx(self.vars["MET_TIMESTAMP_IDX"].get()),
                "MET_WINDSPD_IDX": self.parse_optional_idx(self.vars["MET_WINDSPD_IDX"].get()),
                "MET_WINDDIR_IDX": self.parse_optional_idx(self.vars["MET_WINDDIR_IDX"].get()),
                "MET_EXTERNTEMP_IDX": self.parse_optional_idx(self.vars["MET_EXTERNTEMP_IDX"].get()),
                "MET_SAMPLE_STAMP": self.vars["MET_SAMPLE_STAMP"].get(),
                "FILL_METHOD": self.vars["FILL_METHOD"].get(),
                "NEAREST_TOLERANCE_SEC": int(self.vars["NEAREST_TOLERANCE_SEC"].get()),
                "BACKFILL_BEFORE_FIRST": self.vars["BACKFILL_BEFORE_FIRST"].get() == "True",
                "MET_SPEED_UNITS": self.vars["MET_SPEED_UNITS"].get(),
                "CONVERT_MPH_TO_MPS": self.vars["CONVERT_MPH_TO_MPS"].get() == "True",
                "MET_INVALID_SPEED": {x.strip() for x in self.vars["MET_INVALID_SPEED"].get().split(",") if x.strip()}
            }
        except Exception as e:
            messagebox.showerror("Configuration Error", f"Failed to parse user entries: {e}")
            return

        self._worker_running = True
        self._set_busy(True)
        self._update_progress(0, 1, "Starting…")

        threading.Thread(target=self.run_process, args=(config,), daemon=True).start()

    def run_process(self, config):
        logger = None
        progress = self._make_progress_callback()

        try:
            ensure_dir(config["OUTPUT_DIR"])

            log_ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            log_path = os.path.join(config["OUTPUT_DIR"], f"nvspl_convert_{log_ts}.log")
            logger, log_path = create_file_logger(
                "nvspl_convert",
                log_path,
                [
                    "----- LD821 CSV to NVSPL conversion run started -----",
                    f"Site ID: {config['SITE_ID']} | Input: {config['INPUT_CSV']}",
                ],
            )

            def dual_log(message):
                msg = str(message)
                logger.info(msg)
                self._on_ui(self._append_log, msg)

            dual_log("Starting conversion process...")

            per_day = parse_ld821_to_day_records(config["SITE_ID"], config["INPUT_CSV"])
            days = sorted(per_day.items())
            total_steps = len(days) + 1
            progress(1, total_steps, f"Parsed {len(days)} day(s)")

            met_samples = load_met_samples(config, dual_log) if config["MERGE_MET"] else None

            total_files = 0
            for day_idx, (day, recs) in enumerate(days, start=1):
                progress(day_idx + 1, total_steps, f"Processing day {day_idx} of {len(days)}")

                hour_bundles = parse_daily_file_to_hours(config["SITE_ID"], recs)
                hour_bundles = merge_met_for_day(hour_bundles, config, dual_log, met_samples=met_samples)

                for b in hour_bundles:
                    write_hour_file(config["OUTPUT_DIR"], config["SITE_ID"], b["start"], b["rows"])
                    total_files += 1

                dual_log(f"[WRITE] Day {day} -> {len(hour_bundles)} hourly NVSPL files")

            dual_log(f"\nCompleted! Total NVSPL files created: {total_files}")
            self._on_ui(self._on_success, total_files, config["OUTPUT_DIR"], log_path)

        except Exception as ex:
            if logger:
                logger.exception("Conversion failed")
            self._on_ui(self._append_log, f"\n[ERROR] Conversion failed: {ex}")
            self._on_ui(self._on_failure, str(ex))
        finally:
            if logger:
                close_logger(logger)
            self._on_ui(self._on_worker_done)

    def _on_success(self, total_files, output_dir, log_path):
        total = int(float(self.progress.cget("maximum")))
        self._update_progress(total, total, "Done")
        output_dir = normalize_gui_path(output_dir)
        log_path = normalize_gui_path(log_path)
        self._append_log(
            f"\n--- Result Summary ---\n"
            f"Output directory: {output_dir}\n"
            f"Total NVSPL files created: {total_files}\n"
            f"Log file: {log_path}"
        )
        messagebox.showinfo(
            "LD821 NVSPL — Complete",
            f"LD821 CSV to NVSPL Converter finished successfully.\n\n"
            f"Total files written: {total_files}\n\nOutput saved to:\n{output_dir}",
        )

    def _on_failure(self, error):
        self._reset_progress()
        messagebox.showerror(
            "LD821 NVSPL — Error",
            f"LD821 CSV to NVSPL Converter failed:\n{error}",
        )

# ==============================================================================
# 3. ENTRY POINT
# ==============================================================================

def main():
    app = AppGUI()
    app.mainloop()


if __name__ == "__main__":
    main()