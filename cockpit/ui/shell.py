from __future__ import annotations

import sqlite3
import tkinter as tk

from cockpit.ui.login import LoginWindow


class ShellWindow:
    def __init__(self, *, root: tk.Tk, conn: sqlite3.Connection) -> None:
        self._root = root
        self._conn = conn

    def show(self) -> None:
        LoginWindow(root=self._root, conn=self._conn).show()

