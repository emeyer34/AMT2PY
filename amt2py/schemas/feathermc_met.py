# -*- coding: utf-8 -*-
"""Exact and fuzzy column names for FeatherMC combined MET CSV (NVSPL merge contract)."""

from amt2py.schemas.utils import col_index, header_columns

# Added by FeatherMC_combine.clean_and_format_data
FEATHERMC_COMBINED_TIMESTAMP = "Date-Time (LOC)"
FEATHERMC_ADDED_COLUMNS = ("UTC", FEATHERMC_COMBINED_TIMESTAMP, "Time Zone")

# Raw logger columns preserved by combine (microSD export header strings)
FEATHERMC_WIND_GUST = ("Wind Spd Max", "Gust m/s")
FEATHERMC_WIND_DIR = ("Dir",)
FEATHERMC_TEMP = ("Temp",)


def _header_tokens(header_row):
    return [str(x or "").strip().lower() for x in header_columns(header_row)]


def fuzzy_met_column_indices(header_row, *, infer_wind=True):
    """Substring header matching for MET columns (pre-826f66d behavior)."""
    hdr_tokens = _header_tokens(header_row)
    result = {"ts_idx": None, "spd_idx": None, "dir_idx": None, "tmp_idx": None}

    for i, h in enumerate(hdr_tokens):
        if "date-time (loc)" in h:
            result["ts_idx"] = i
            break
    if result["ts_idx"] is None:
        for i, h in enumerate(hdr_tokens):
            if h == "timestamp" or h.endswith(" timestamp"):
                result["ts_idx"] = i
                break

    if infer_wind:
        for i, h in enumerate(hdr_tokens):
            if "gust" in h:
                result["spd_idx"] = i
                break
        if result["spd_idx"] is None:
            for i, h in enumerate(hdr_tokens):
                if h == "spd" or "speed" in h or h == "avg":
                    result["spd_idx"] = i
                    break

    for i, h in enumerate(hdr_tokens):
        if "dir" in h and "time" not in h and "date" not in h:
            result["dir_idx"] = i
            break

    for i, h in enumerate(hdr_tokens):
        if "temp" in h or "adc1" in h:
            result["tmp_idx"] = i
            break

    return result


def _merge_runtime_indices(exact, fuzzy):
    return {
        key: exact[key] if exact.get(key) is not None else fuzzy.get(key)
        for key in ("ts_idx", "spd_idx", "dir_idx", "tmp_idx")
    }


def is_feathermc_combined_header(header_row):
    return FEATHERMC_COMBINED_TIMESTAMP in header_columns(header_row)


def infer_feathermc_met_gui_indices(header_row):
    """Exact header-name lookup, with fuzzy fallback for alternate logger names."""
    cols = header_columns(header_row)
    ts_i = col_index(cols, (FEATHERMC_COMBINED_TIMESTAMP,))
    gust_i = col_index(cols, FEATHERMC_WIND_GUST)
    dir_i = col_index(cols, FEATHERMC_WIND_DIR)
    tmp_i = col_index(cols, FEATHERMC_TEMP)

    exact = {
        "MET_TIMESTAMP_IDX": str(ts_i) if ts_i is not None else "",
        "MET_WINDSPD_IDX": str(gust_i) if gust_i is not None else "",
        "MET_WINDDIR_IDX": str(dir_i) if dir_i is not None else "None",
        "MET_EXTERNTEMP_IDX": str(tmp_i) if tmp_i is not None else "None",
    }
    fuzzy = fuzzy_met_column_indices(header_row)

    def _pick(exact_val, fuzzy_idx):
        if exact_val and exact_val not in ("", "None"):
            return exact_val
        return str(fuzzy_idx) if fuzzy_idx is not None else exact_val

    return {
        "MET_TIMESTAMP_IDX": _pick(exact["MET_TIMESTAMP_IDX"], fuzzy["ts_idx"]),
        "MET_WINDSPD_IDX": _pick(exact["MET_WINDSPD_IDX"], fuzzy["spd_idx"]),
        "MET_WINDDIR_IDX": _pick(exact["MET_WINDDIR_IDX"], fuzzy["dir_idx"]),
        "MET_EXTERNTEMP_IDX": _pick(exact["MET_EXTERNTEMP_IDX"], fuzzy["tmp_idx"]),
    }


def feathermc_met_runtime_indices(header_row):
    """Exact names first, then legacy fuzzy fallbacks on the same header."""
    cols = header_columns(header_row)
    exact = {
        "ts_idx": col_index(cols, (FEATHERMC_COMBINED_TIMESTAMP,)),
        "spd_idx": col_index(cols, FEATHERMC_WIND_GUST),
        "dir_idx": col_index(cols, FEATHERMC_WIND_DIR),
        "tmp_idx": col_index(cols, FEATHERMC_TEMP),
    }
    fuzzy = fuzzy_met_column_indices(header_row)
    return _merge_runtime_indices(exact, fuzzy)
