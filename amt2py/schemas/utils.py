# -*- coding: utf-8 -*-
"""Shared helpers for CSV header / column index lookup and GUI paths."""

import os


def normalize_gui_path(path):
    """Use forward slashes in GUI path fields and user-visible output.

    Safe for Python file APIs on Windows; paste into Explorer's address bar works too.
    """
    if not path:
        return path
    return os.path.normpath(path).replace("\\", "/")


def header_columns(header_row):
    return [str(c or "").strip() for c in (header_row or [])]


def col_index(cols, names):
    """First exact match among *names* in cols, or None."""
    for name in names:
        if name in cols:
            return cols.index(name)
    return None
