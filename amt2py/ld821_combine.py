# -*- coding: utf-8 -*-
import os
import re
import csv
import logging
import threading
from datetime import datetime

import pandas as pd
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from amt2py.shared_gui_components import (
    ToolTip,
    WorkerGuiMixin,
    close_logger,
    create_file_logger,
    pack_combine_layout,
)
from amt2py.schemas.ld821_spl import (
    LD821_COMBINED_BASENAME,
    LD821_HEADER_MARKER,
    is_ld821_time_history_header,
    ld821_csv_header_line_index,
)
from amt2py.schemas.utils import normalize_gui_path

# Compile regex pattern to match: ...Time History[ optional number ].csv
TIME_HISTORY_PATTERN = re.compile(r'Time History(?:\s*\d+)?\.csv$', re.IGNORECASE)

# ------------------------------------------------------------------------------
# Core Processing Functions
# ------------------------------------------------------------------------------
def setup_logger(output_dir: str, sitename: str, selected_folder: str):
    log_ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_path = os.path.join(output_dir, f"combine_slm_{log_ts}.log")
    return create_file_logger(
        "combine_slm",
        log_path,
        [
            "----- Combine SLM Time History run started -----",
            f"Sitename: {sitename} | Selected folder: {selected_folder}",
        ],
    )

def find_time_column(df: pd.DataFrame) -> str:
    col, _ = find_time_column_and_series(df)
    return col

def find_time_column_and_series(df: pd.DataFrame):
    # First pass: columns that look like time/date/timestamp
    name_candidates = [c for c in df.columns if re.search(r'(time|date|timestamp)', str(c), re.IGNORECASE)]
    for c in name_candidates:
        parsed = pd.to_datetime(df[c], errors='coerce')
        if parsed.notna().any():
            return c, parsed

    # Second pass: try to parse each column as datetime
    for c in df.columns:
        parsed = pd.to_datetime(df[c], errors='coerce')
        if parsed.notna().any():
            return c, parsed

    # Fallbacks
    if len(df.columns) >= 2:
        c = df.columns[1]
    else:
        c = df.columns[0]
    return c, pd.to_datetime(df[c], errors='coerce')

def read_time_history_csv(path: str, logger: logging.Logger) -> pd.DataFrame:
    """Read G4 Time History CSV, skipping metadata lines before Record Type header."""
    skip = ld821_csv_header_line_index(path)
    if skip is None:
        raise ValueError(
            f"Could not find G4 header ({LD821_HEADER_MARKER!r}) in {os.path.basename(path)}"
        )
    if skip:
        logger.info(f"Skipping {skip} preamble line(s) before G4 header in {os.path.basename(path)}")
        df = pd.read_csv(path, skiprows=range(skip), header=0, encoding="utf-8-sig")
    else:
        df = pd.read_csv(path, encoding="utf-8-sig")
    if not is_ld821_time_history_header(list(df.columns)):
        preview = ", ".join(str(c) for c in list(df.columns)[:8])
        raise ValueError(
            f"Columns after reading {os.path.basename(path)} do not look like G4 Time History: {preview}"
        )
    return df

def process_slm_files(selected_files: list, sitename: str, logger: logging.Logger, output_dir: str, progress_callback=None):
    n = len(selected_files)
    total = n + 2

    def report(step, msg):
        if progress_callback:
            progress_callback(step, total, msg)

    logger.info(f"Files matched Time History pattern: {n}")
    for f in selected_files:
        logger.info(f"  ✔ {f}")

    report(0, "Starting…")

    # Read CSVs
    dfs = []
    for i, f in enumerate(selected_files):
        report(i + 1, f"Reading file {i + 1} of {n}…")
        try:
            df = read_time_history_csv(f, logger)
            dfs.append(df)
            logger.info(f"Read OK: {f} | Rows: {len(df)} | Columns: {list(df.columns)}")
        except Exception as e:
            logger.error(f"Failed to read {f}: {e}")
            raise

    report(n + 1, "Combining and sorting…")

    # Combine into a single DataFrame
    data = pd.concat(dfs, ignore_index=True)
    logger.info(f"Combined DataFrame rows: {len(data)}; columns: {list(data.columns)}")

    # Sort by time column
    time_col, parsed = find_time_column_and_series(data)
    logger.info(f"Detected time column: '{time_col}'")

    nat_count = parsed.isna().sum()
    logger.info(f"Non-parsable timestamps (NaT) before sort: {nat_count}")

    data[time_col] = parsed
    data = data.sort_values(by=time_col, kind='stable').reset_index(drop=True)
    logger.info("Data sorted by time column.")

    # Output naming — always write to the folder the user selected in the GUI
    base_fname = os.path.basename(selected_files[-1])
    standardized_fname = re.sub(
        r'Time History(?:\s*\d+)?\.csv$', 'Time History.csv',
        base_fname, flags=re.IGNORECASE
    )
    output_fname = f"{sitename}_{standardized_fname}"
    output_path = os.path.join(output_dir, output_fname)

    report(n + 2, "Writing output…")

    # Write CSV
    data.to_csv(output_path, index=False, quoting=csv.QUOTE_NONE, escapechar='\\')
    logger.info(f"Output written: {output_path}")
    logger.info(
        f"NVSPL hint: browse this file in ld821_to_nvspl.py — SITE_ID autofill expects "
        f"prefix before _{LD821_COMBINED_BASENAME!r} (e.g. {sitename!r}); "
        f"header must include {LD821_HEADER_MARKER!r}"
    )
    logger.info("----- Combine SLM Time History run completed -----")
    return output_path

# ------------------------------------------------------------------------------
# Main Application GUI
# ------------------------------------------------------------------------------
class LD821CombineApp(WorkerGuiMixin, tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LD821 Time History Combiner")
        self.geometry("560x520")
        self.minsize(480, 440)
        self.resizable(True, True)

        self.selected_folder = ""
        self.matched_files = []
        self.init_worker_state()
        self._build_gui()

    def _build_gui(self):
        main_frame = ttk.Frame(self, padding="12")
        main_frame.pack(fill=tk.BOTH, expand=True)

        content = pack_combine_layout(main_frame, self)

        # --- Folder Selector Group ---
        grp_folder = ttk.LabelFrame(content, text=" RAW Folder Selector ", padding="10")
        grp_folder.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        btn_browse = ttk.Button(grp_folder, text="Select High-Level Directory Where Time History Files Live (e.g. RAW)...", command=self.browse_folder)
        btn_browse.pack(anchor="w", pady=(0, 5))
        self.btn_browse = btn_browse

        self.lbl_folder_status = ttk.Label(grp_folder, text="No folder selected", font=("Segoe UI", 9, "italic"))
        self.lbl_folder_status.pack(anchor="w", pady=(0, 2))

        # Listbox displaying downstream matched Time History files
        list_frame = ttk.Frame(grp_folder)
        list_frame.pack(fill=tk.BOTH, expand=True)

        self.lst_files = tk.Listbox(list_frame, height=6, selectmode=tk.EXTENDED)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.lst_files.yview)
        self.lst_files.configure(yscrollcommand=scrollbar.set)

        self.lst_files.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # --- Metadata Inputs Group ---
        grp_meta = ttk.LabelFrame(content, text=" Site Settings ", padding="10")
        grp_meta.pack(fill=tk.X, pady=(0, 5))

        # sitename
        lbl_site = ttk.Label(grp_meta, text="Site Name:", width=18, anchor="w")
        lbl_site.grid(row=0, column=0, sticky="w", pady=4)
        self.var_sitename = tk.StringVar(value="PARK001")
        ent_site = ttk.Entry(grp_meta, textvariable=self.var_sitename)
        ent_site.grid(row=0, column=1, sticky="ew", padx=5, pady=4)
        grp_meta.columnconfigure(1, weight=1)
        hint_site = "Used in output filename (e.g. DENATRLA)"
        ToolTip(ent_site, hint_site)
        ToolTip(lbl_site, hint_site)

    def browse_folder(self):
        if self._worker_running:
            return
        folder = filedialog.askdirectory(title="Select High-Level Directory (RAW)")
        if not folder:
            return

        self.selected_folder = folder
        self.matched_files = []
        self.lst_files.delete(0, tk.END)
        self._set_result("")

        # Recursively search for matching "Time History" CSV files
        for root, _, filenames in os.walk(folder):
            for f in filenames:
                if TIME_HISTORY_PATTERN.search(f):
                    full_path = os.path.join(root, f)
                    self.matched_files.append(full_path)

        if self.matched_files:
            self.lbl_folder_status.config(
                text=f"Found {len(self.matched_files)} 'Time History' file(s) in {os.path.basename(folder)}"
            )
            for f in self.matched_files:
                rel_path = os.path.relpath(f, folder)
                self.lst_files.insert(tk.END, rel_path)
        else:
            self.lbl_folder_status.config(text="No matching 'Time History' CSV files found in directory.")
            messagebox.showwarning(
                "No Matching Files",
                f"No CSV files ending with 'Time History.csv' (or 'Time History 1.csv', etc.) were found in:\n{folder}"
            )

    def run_process(self):
        if self._worker_running:
            return
        if not self.matched_files:
            messagebox.showwarning("Missing Input", "Please select a directory containing 'Time History' CSV files first.")
            return

        sitename = self.var_sitename.get().strip()

        source_dirs = {os.path.dirname(f) for f in self.matched_files}
        if len(source_dirs) > 1:
            proceed = messagebox.askyesno(
                "Multiple source folders",
                f"Time History files were found in {len(source_dirs)} different subfolders.\n\n"
                "Please confirm these are the files you want to combine.\n\n"
                "Continue?"
            )
            if not proceed:
                return

        output_dir = self.selected_folder
        files = list(self.matched_files)

        self._worker_running = True
        self._set_busy(True)
        self._set_result("")
        self._update_progress(0, 1, "Starting…")

        threading.Thread(
            target=self._run_worker,
            args=(output_dir, sitename, files),
            daemon=True,
        ).start()

    def _run_worker(self, output_dir, sitename, files):
        logger = None
        progress = self._make_progress_callback()

        try:
            logger, log_path = setup_logger(output_dir, sitename, self.selected_folder)
            output_path = process_slm_files(
                files, sitename, logger, output_dir,
                progress_callback=progress,
            )
            self._on_ui(self._on_success, output_path, log_path, len(files))
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
            f"LD821 combine done — {file_count} file(s)\n"
            f"Output: {output_path}\n"
            f"Log: {log_path}",
            ok=True,
        )
        messagebox.showinfo(
            "LD821 Combine — Complete",
            f"LD821 Time History Combiner finished successfully.\n\n"
            f"Combined {file_count} file(s).\n\nOutput saved to:\n{output_path}"
        )

    def _on_failure(self, error):
        self._reset_progress()
        self._set_result(f"Failed — {error}", ok=False)
        messagebox.showerror(
            "LD821 Combine — Error",
            f"LD821 Time History Combiner failed:\n{error}"
        )

# ------------------------------------------------------------------------------
# Entry Point
# ------------------------------------------------------------------------------
def main():
    app = LD821CombineApp()
    app.mainloop()


if __name__ == "__main__":
    main()
