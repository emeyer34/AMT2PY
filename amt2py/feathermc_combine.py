# -*- coding: utf-8 -*-
import os
import re
import csv
import logging
import threading
from datetime import datetime

import pandas as pd
import pytz
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from amt2py.shared_gui_components import (
    ToolTip,
    WorkerGuiMixin,
    close_logger,
    create_file_logger,
    pack_combine_layout,
)
from amt2py.schemas.feathermc_met import FEATHERMC_COMBINED_TIMESTAMP, FEATHERMC_WIND_GUST
from amt2py.schemas.utils import normalize_gui_path

# Timezone definitions
COMMON_TZS = [
    "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles",
    "America/Phoenix", "America/Anchorage", "America/Honolulu",
    "UTC", "Europe/London", "Europe/Berlin", "Europe/Paris",
    "Asia/Tokyo", "Asia/Shanghai", "Australia/Sydney"
]

try:
    all_tzs = [tz for tz in pytz.all_timezones if tz not in COMMON_TZS]
    TIMEZONE_LIST = COMMON_TZS + all_tzs
except Exception:
    TIMEZONE_LIST = COMMON_TZS

# Combined output from this script: "{serial} {YYYY-MM-DD HHMMSS}.csv"
COMBINED_OUTPUT_PATTERN = re.compile(
    r'^\d+\s+\d{4}-\d{2}-\d{2}\s+\d{6}\.csv$', re.IGNORECASE
)

def _read_csv_header(path: str) -> list:
    with open(path, 'r', encoding='utf-8', errors='replace', newline='') as f:
        return next(csv.reader(f), [])

def is_raw_logger_csv(path: str) -> bool:
    """MicroSD logger export — not a prior combined output from this tool."""
    name = os.path.basename(path)
    if COMBINED_OUTPUT_PATTERN.match(name):
        return False
    try:
        cols = {c.strip() for c in _read_csv_header(path)}
    except OSError:
        return False
    if 'Date-Time (UTC)' not in cols:
        return False
    if 'Date-Time (LOC)' in cols:
        return False
    return True

def find_raw_logger_csvs(folder: str):
    """Return (matched paths, skipped combined names, skipped other names)."""
    matched = []
    skipped_combined = []
    skipped_other = []
    for name in sorted(os.listdir(folder)):
        if not name.lower().endswith('.csv'):
            continue
        full = os.path.join(folder, name)
        if not os.path.isfile(full):
            continue
        if COMBINED_OUTPUT_PATTERN.match(name):
            skipped_combined.append(name)
            continue
        if is_raw_logger_csv(full):
            matched.append(full)
        else:
            skipped_other.append(name)
    return matched, skipped_combined, skipped_other

# ------------------------------------------------------------------------------
# Core Processing Functions
# ------------------------------------------------------------------------------
def setup_logger(output_dir: str, site_name: str, serial: str, selected_folder: str):
    log_ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_path = os.path.join(output_dir, f"feathermc_clean_{log_ts}.log")
    return create_file_logger(
        "feathermc_clean",
        log_path,
        [
            "----- FeatherMC wind clean prep run started -----",
            f"Site: {site_name} | Serial: {serial} | Selected folder: {selected_folder}",
        ],
    )

def read_and_combine_files(file_paths, logger: logging.Logger, progress_callback=None) -> pd.DataFrame:
    if not file_paths:
        raise ValueError("No files were selected.")

    n = len(file_paths)
    total = n + 2

    def report(step, msg):
        if progress_callback:
            progress_callback(step, total, msg)

    logger.info(f"Total files selected: {n}")
    for f in file_paths:
        logger.info(f"  - {f}")

    dfs = []
    for i, f in enumerate(file_paths):
        report(i + 1, f"Reading file {i + 1} of {n}…")
        try:
            df = pd.read_csv(f)
            dfs.append(df)
            logger.info(f"Read OK: {f} | Rows: {len(df)} | Columns: {list(df.columns)}")
        except Exception as e:
            logger.error(f"Failed to read {f}: {e}")
            raise

    combined_df = pd.concat(dfs, ignore_index=True)
    logger.info(f"Combined DataFrame rows: {len(combined_df)}; columns: {list(combined_df.columns)}")
    return combined_df

def clean_repeated_headers(df: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    if '#' not in df.columns:
        msg = "Required column '#' not found."
        logger.error(msg)
        raise ValueError(msg)
    before = len(df)
    df_clean = df[pd.to_numeric(df['#'], errors='coerce').notnull()].copy()
    after = len(df_clean)
    removed = before - after
    logger.info(f"Removed {removed} repeated header/corrupt rows based on '#' column.")
    return df_clean

def convert_utc_to_local(utc_series: pd.Series, tz_name: str, adjust_dst: bool, logger: logging.Logger):
    local_tz = pytz.timezone(tz_name)
    utc_aware = utc_series.dt.tz_localize('UTC')

    if adjust_dst:
        local_times = utc_aware.dt.tz_convert(local_tz)
        tz_abbr = local_times.dt.strftime('%Z')
        logger.info(f"Converted timestamps from UTC to {tz_name} with DST rules applied.")
    else:
        standard_offset = local_tz.utcoffset(datetime(2025, 1, 1))
        local_times = utc_aware.dt.tz_localize(None) + standard_offset
        tz_abbr_val = local_tz.localize(datetime(2025, 1, 1)).tzname()
        tz_abbr = [tz_abbr_val] * len(local_times)
        logger.info(f"Converted timestamps from UTC to {tz_name} using a fixed standard-time offset (no DST).")

    return local_times, tz_abbr

def clean_and_format_data(df: pd.DataFrame, tz: str, adjust_dst: bool, logger: logging.Logger) -> pd.DataFrame:
    df = clean_repeated_headers(df, logger)

    if 'Date-Time (UTC)' not in df.columns:
        msg = "Required column 'Date-Time (UTC)' not found."
        logger.error(msg)
        raise ValueError(msg)

    df['UTC'] = pd.to_datetime(df['Date-Time (UTC)'], errors='coerce')
    nat_before = df['UTC'].isna().sum()
    if nat_before:
        logger.info(f"Rows with non-parsable UTC timestamps: {nat_before}")
    df = df.dropna(subset=['UTC']).copy()

    local_time, tz_abbr = convert_utc_to_local(df['UTC'], tz, adjust_dst, logger)
    df['Date-Time (LOC)'] = local_time.dt.strftime('%m/%d/%Y %H:%M:%S')
    df['Time Zone'] = tz_abbr

    unique_abbr = pd.Series(tz_abbr).unique().tolist()
    logger.info(f"Time zone abbreviations present after conversion: {unique_abbr}")

    if '#' in df.columns:
        df['#'] = pd.to_numeric(df['#'], errors='coerce')

    df['_loc_dt'] = pd.to_datetime(df['Date-Time (LOC)'], format='%m/%d/%Y %H:%M:%S', errors='coerce')
    nat_loc = df['_loc_dt'].isna().sum()
    if nat_loc:
        logger.info(f"Non-parsable local timestamps during sort: {nat_loc} (these rows will sort last).")

    df = df.sort_values(by='_loc_dt', kind='stable').drop(columns=['_loc_dt']).reset_index(drop=True)
    logger.info("Data sorted by 'Date-Time (LOC)'.")

    if len(df) > 0:
        logger.info(f"First local time: {df['Date-Time (LOC)'].iloc[0]} | "
                    f"Last local time: {df['Date-Time (LOC)'].iloc[-1]}")

    return df

def export_data(df: pd.DataFrame, output_dir: str, serial: str, logger: logging.Logger):
    if df.empty:
        msg = "No valid data rows remain after cleaning and UTC conversion."
        logger.error(msg)
        raise ValueError(msg)
    last_date_str = df['Date-Time (LOC)'].iloc[-1]
    last_dt = datetime.strptime(last_date_str, "%m/%d/%Y %H:%M:%S")
    formatted_date = last_dt.strftime("%Y-%m-%d %H%M%S")
    filename = f"{serial} {formatted_date}.csv"
    output_path = os.path.join(output_dir, filename)
    df.to_csv(output_path, index=False)
    logger.info(f"All columns written to output: {list(df.columns)}")
    if "Date-Time (LOC)" in df.columns:
        loc_i = list(df.columns).index("Date-Time (LOC)")
        gust_name = next((n for n in FEATHERMC_WIND_GUST if n in df.columns), FEATHERMC_WIND_GUST[0])
        gust_i = list(df.columns).index(gust_name) if gust_name in df.columns else "?"
        logger.info(
            f"NVSPL merge hint: timestamp col {loc_i} ({FEATHERMC_COMBINED_TIMESTAMP!r}), "
            f"wind gust col {gust_i} ({gust_name!r}) — auto-filled in ld821_to_nvspl.py"
        )
    logger.info(f"Output written: {output_path}")
    logger.info("----- FeatherMC wind clean prep run completed -----")
    return output_path

# ------------------------------------------------------------------------------
# Main Application GUI
# ------------------------------------------------------------------------------
class FeatherMCApp(WorkerGuiMixin, tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("FeatherMC Wind Data Combination Tool")
        self.geometry("560x600")
        self.minsize(480, 480)
        self.resizable(True, True)

        self.selected_folder = ""
        self.matched_files = []
        self.init_worker_state()
        self._build_gui()

    def _build_gui(self):
        main_frame = ttk.Frame(self, padding="12")
        main_frame.pack(fill=tk.BOTH, expand=True)

        content = pack_combine_layout(main_frame, self)

        # --- File Selector Group ---
        grp_files = ttk.LabelFrame(content, text=" MET Folder Selector ", padding="10")
        grp_files.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        btn_browse = ttk.Button(
            grp_files,
            text="Select MET Folder (logger CSVs; combined outputs skipped automatically)...",
            command=self.browse_folder,
        )
        btn_browse.pack(anchor="w", pady=(0, 5))
        self.btn_browse = btn_browse

        self.lbl_file_count = ttk.Label(grp_files, text="No folder selected", font=("Segoe UI", 9, "italic"))
        self.lbl_file_count.pack(anchor="w", pady=(0, 2))

        # Listbox to display selected file paths
        list_frame = ttk.Frame(grp_files)
        list_frame.pack(fill=tk.BOTH, expand=True)

        self.lst_files = tk.Listbox(list_frame, height=5, selectmode=tk.EXTENDED)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.lst_files.yview)
        self.lst_files.configure(yscrollcommand=scrollbar.set)

        self.lst_files.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # --- User Input & Metadata Group ---
        grp_meta = ttk.LabelFrame(content, text=" Site Settings ", padding="10")
        grp_meta.pack(fill=tk.X, pady=(0, 5))

        # site_name
        lbl_site = ttk.Label(grp_meta, text="Site Name:", width=18, anchor="w")
        lbl_site.grid(row=0, column=0, sticky="w", pady=4)
        self.var_site_name = tk.StringVar(value="PARK001")
        ent_site = ttk.Entry(grp_meta, textvariable=self.var_site_name)
        ent_site.grid(row=0, column=1, sticky="ew", padx=5, pady=4)
        grp_meta.columnconfigure(1, weight=1)
        hint_site = "Optional log metadata (e.g. DENATRLA)"
        ToolTip(ent_site, hint_site)
        ToolTip(lbl_site, hint_site)

        # serial
        lbl_serial = ttk.Label(grp_meta, text="Serial Number:", width=18, anchor="w")
        lbl_serial.grid(row=1, column=0, sticky="w", pady=4)
        self.var_serial = tk.StringVar(value="00000018")
        ent_serial = ttk.Entry(grp_meta, textvariable=self.var_serial)
        ent_serial.grid(row=1, column=1, sticky="ew", padx=5, pady=4)
        hint_serial = "Located in metadata files"
        ToolTip(ent_serial, hint_serial)
        ToolTip(lbl_serial, hint_serial)

        # --- Timezone & DST Group ---
        grp_tz = ttk.LabelFrame(content, text=" Time Zone & DST Handling ", padding="10")
        grp_tz.pack(fill=tk.X, pady=(0, 5))

        lbl_tz = ttk.Label(grp_tz, text="Time Zone:", width=18, anchor="w")
        lbl_tz.grid(row=0, column=0, sticky="w", pady=4)
        self.var_tzone = tk.StringVar(value="America/Denver")
        cmb_tz = ttk.Combobox(grp_tz, textvariable=self.var_tzone, values=TIMEZONE_LIST, state="readonly")
        cmb_tz.grid(row=0, column=1, sticky="ew", padx=5, pady=4)
        grp_tz.columnconfigure(1, weight=1)

        self.var_dst = tk.BooleanVar(value=False)
        chk_dst = ttk.Checkbutton(
            grp_tz,
            text="Adjust for DST (apply local DST rules vs fixed standard offset)",
            variable=self.var_dst
        )
        chk_dst.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))

    def browse_folder(self):
        if self._worker_running:
            return
        folder = filedialog.askdirectory(title="Select MET Folder")
        if not folder:
            return

        self.selected_folder = folder
        self.matched_files = []
        self.lst_files.delete(0, tk.END)
        self._set_result("")

        matched, skipped_combined, skipped_other = find_raw_logger_csvs(folder)

        if matched:
            self.matched_files = matched
            parts = [f"Found {len(matched)} logger CSV(s) in {os.path.basename(folder)}"]
            if skipped_combined:
                parts.append(f"skipped {len(skipped_combined)} combined output(s)")
            if skipped_other:
                parts.append(f"skipped {len(skipped_other)} other CSV(s)")
            self.lbl_file_count.config(text=" — ".join(parts))
            for f in matched:
                self.lst_files.insert(tk.END, os.path.basename(f))
        else:
            self.lbl_file_count.config(text="No raw logger CSVs found in folder.")
            detail = (
                "No microSD logger CSVs found.\n\n"
                "This folder may only contain prior combined outputs or unrelated CSVs.\n"
                "Combined files (named like '00000018 2026-07-09 125259.csv') and files "
                "without a 'Date-Time (UTC)' column are skipped automatically."
            )
            if skipped_combined or skipped_other:
                detail += f"\n\nSkipped: {len(skipped_combined)} combined, {len(skipped_other)} other."
            messagebox.showwarning("No Logger CSVs Found", detail)

    def run_process(self):
        if self._worker_running:
            return
        if not self.matched_files:
            messagebox.showwarning(
                "Missing Input",
                "Please select a MET folder containing raw logger CSV files first."
            )
            return

        site_name = self.var_site_name.get().strip()
        serial = self.var_serial.get().strip()
        deploy_tzone = self.var_tzone.get().strip()
        adjust_for_dst = self.var_dst.get()

        output_dir = self.selected_folder
        files = list(self.matched_files)

        self._worker_running = True
        self._set_busy(True)
        self._set_result("")
        self._update_progress(0, 1, "Starting…")

        threading.Thread(
            target=self._run_worker,
            args=(output_dir, site_name, serial, deploy_tzone, adjust_for_dst, files),
            daemon=True,
        ).start()

    def _run_worker(self, output_dir, site_name, serial, deploy_tzone, adjust_for_dst, files):
        logger = None
        n = len(files)
        total = n + 2
        progress = self._make_progress_callback()

        try:
            logger, log_path = setup_logger(output_dir, site_name, serial, self.selected_folder)
            logger.info(f"Time zone selected: {deploy_tzone} | adjust_for_dst={adjust_for_dst}")

            raw_data = read_and_combine_files(files, logger, progress_callback=progress)
            progress(n + 1, total, "Cleaning and converting timestamps…")
            clean_data = clean_and_format_data(raw_data, deploy_tzone, adjust_for_dst, logger)
            progress(n + 2, total, "Writing output…")
            output_path = export_data(clean_data, output_dir, serial, logger)

            self._on_ui(self._on_success, output_path, log_path, n)
        except Exception as e:
            self._on_ui(self._on_failure, str(e))
        finally:
            if logger:
                close_logger(logger)
            self._on_ui(self._on_worker_done)

    def _on_success(self, output_path, log_path, file_count):
        total = int(float(self.progress.cget("maximum")))
        self._update_progress(total, total, "Done")
        output_path = normalize_gui_path(output_path)
        log_path = normalize_gui_path(log_path)
        self._set_result(
            f"FeatherMC combine done — {file_count} file(s)\n"
            f"Output: {output_path}\n"
            f"Log: {log_path}",
            ok=True,
        )
        messagebox.showinfo(
            "FeatherMC Combine — Complete",
            f"FeatherMC Wind Combiner finished successfully.\n\n"
            f"Combined {file_count} file(s).\n\nOutput saved to:\n{output_path}"
        )

    def _on_failure(self, error):
        self._reset_progress()
        self._set_result(f"Failed — {error}", ok=False)
        messagebox.showerror(
            "FeatherMC Combine — Error",
            f"FeatherMC Wind Combiner failed:\n{error}"
        )

# ------------------------------------------------------------------------------
# Entry Point
# ------------------------------------------------------------------------------
def main():
    app = FeatherMCApp()
    app.mainloop()


if __name__ == "__main__":
    main()
