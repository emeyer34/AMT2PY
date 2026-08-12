# -*- coding: utf-8 -*-
import logging
import os
from logging import Formatter, StreamHandler, FileHandler

import tkinter as tk
from tkinter import ttk

from amt2py.schemas.utils import normalize_gui_path


class ToolTip:
    """Hover tooltip for a widget."""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.widget.bind("<Enter>", self.show_tip)
        self.widget.bind("<Leave>", self.hide_tip)

    def show_tip(self, event=None):
        if self.tip_window or not self.text:
            return
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            tw, text=self.text, justify=tk.LEFT, background="#ffffe0",
            relief=tk.SOLID, borderwidth=1, font=("tahoma", "8", "normal"),
        )
        label.pack(ipadx=1)

    def hide_tip(self, event=None):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None


def create_file_logger(logger_name, log_path, header_lines):
    log_path = os.path.normpath(log_path)
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler = StreamHandler()
    file_handler = FileHandler(log_path, encoding="utf-8")
    console_handler.setFormatter(fmt)
    file_handler.setFormatter(fmt)
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    for line in header_lines:
        logger.info(line)
    display_log_path = normalize_gui_path(log_path)
    logger.info(f"Log file: {display_log_path}")
    return logger, display_log_path


def close_logger(logger):
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)


def add_scrolled_text(parent, height=4, expand=True, **text_kwargs):
    """Text widget with vertical scrollbar."""
    frame = ttk.Frame(parent)
    frame.pack(fill=tk.BOTH, expand=expand)

    text = tk.Text(frame, height=height, wrap=tk.WORD, **text_kwargs)
    scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=text.yview)
    text.configure(yscrollcommand=scrollbar.set)
    text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    return text


def pack_combine_layout(main_frame, app, run_label="Combine and Process Files"):
    """Pin run/progress/result footer at bottom; return scrollable content frame."""
    footer = ttk.Frame(main_frame)
    footer.pack(side=tk.BOTTOM, fill=tk.X)
    add_run_status_panel(app, footer, run_label)

    content = ttk.Frame(main_frame)
    content.pack(fill=tk.BOTH, expand=True)
    return content


def add_progress_bar(parent, app):
    """Progress label and bar (e.g. above a log panel)."""
    app.lbl_progress = ttk.Label(parent, text="", font=("Segoe UI", 9))
    app.lbl_progress.pack(fill=tk.X, pady=(0, 2))

    app.progress = ttk.Progressbar(parent, mode="determinate", maximum=100)
    app.progress.pack(fill=tk.X, pady=(0, 6))


def add_run_status_panel(app, parent, run_label="Combine and Process Files"):
    """Run button, progress bar, and scrollable copyable result text on *app*."""
    app.btn_run = ttk.Button(parent, text=run_label, command=app.run_process)
    app.btn_run.pack(fill=tk.X, pady=(8, 4))

    app.lbl_progress = ttk.Label(parent, text="", font=("Segoe UI", 9))
    app.lbl_progress.pack(fill=tk.X, pady=(0, 2))

    app.progress = ttk.Progressbar(parent, mode="determinate", maximum=100)
    app.progress.pack(fill=tk.X, pady=(0, 4))

    app.lbl_result = tk.Label(
        parent, text="Result (select text to copy):", anchor="w",
        font=("Segoe UI", 9), foreground="#444444",
    )
    app.lbl_result.pack(fill=tk.X, pady=(0, 2))

    app.txt_result = add_scrolled_text(
        parent,
        height=3,
        expand=True,
        font=("Segoe UI", 9),
        relief=tk.GROOVE,
        borderwidth=1,
        padx=4,
        pady=4,
        foreground="#666666",
    )
    app.txt_result.bind("<Key>", app._result_text_key)


class WorkerGuiMixin:
    """Thread-safe progress/result UI for folder-browse combine apps."""

    def init_worker_state(self):
        self._worker_running = False

    def _on_ui(self, func, *args, **kwargs):
        self.after(0, lambda: func(*args, **kwargs))

    def _update_progress(self, step, total, message):
        self.progress.config(maximum=total, value=step)
        self.lbl_progress.config(text=message)

    def _reset_progress(self):
        self.progress.config(value=0)
        self.lbl_progress.config(text="")

    def _result_text_key(self, event):
        mod = event.state & 0x4 or event.state & 0x8
        if mod and event.keysym.lower() in ("c", "a"):
            return
        return "break"

    def _set_result(self, text, ok=None):
        if ok is True:
            color = "#1a7f37"
        elif ok is False:
            color = "#b42318"
        else:
            color = "#666666"
        self.txt_result.config(fg=color)
        self.txt_result.delete("1.0", tk.END)
        if text:
            self.txt_result.insert("1.0", text)

    def _set_run_busy(self, busy, idle_text="Run Conversion Process"):
        if busy:
            self.btn_run.config(state=tk.DISABLED, text="Processing…")
        else:
            self.btn_run.config(state=tk.NORMAL, text=idle_text)

    def _set_busy(self, busy):
        if busy:
            self.btn_run.config(state=tk.DISABLED, text="Processing…")
            self.btn_browse.config(state=tk.DISABLED)
        else:
            self.btn_run.config(state=tk.NORMAL, text="Combine and Process Files")
            self.btn_browse.config(state=tk.NORMAL)

    def _on_worker_done(self):
        self._worker_running = False
        self._set_busy(False)
        if float(self.progress.cget("value")) < float(self.progress.cget("maximum")):
            self._reset_progress()

    def _make_progress_callback(self):
        def progress(step, total, message):
            self._on_ui(self._update_progress, step, total, message)
        return progress
