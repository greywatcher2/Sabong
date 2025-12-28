from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import messagebox
from tkinter import ttk

from cockpit.db.connection import transaction
from cockpit.services.audit import Actor
from cockpit.services.auth import AuthService
from cockpit.services.operations import OperationsService
from cockpit.services.rbac import RBACService
from cockpit.ui.main_window import MainWindow
from cockpit.ui.common import palette
from cockpit.utils.device import get_device_id


class LoginWindow:
    def __init__(self, *, root: tk.Tk, conn: sqlite3.Connection) -> None:
        self._root = root
        self._conn = conn
        self._device_id = get_device_id()

        bg = root.cget("bg")
        self._frame = tk.Frame(root, bg=bg)
        self._shell = tk.Frame(self._frame, bg=bg)
        self._username = tk.StringVar()
        self._password = tk.StringVar()

    def show(self) -> None:
        self._root.protocol("WM_DELETE_WINDOW", self._root.destroy)
        self._frame.pack(fill="both", expand=True)
        self._shell.place(relx=0.5, rely=0.5, anchor="center")

        p = palette()
        card_outer = tk.Frame(self._shell, bg=p["shadow"])
        card_outer.pack()
        card = tk.Frame(card_outer, bg=p["surface"])
        card.pack(padx=1, pady=1)

        ttk.Label(card, text="Welcome back", style="Title.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", padx=18, pady=(18, 6))
        ttk.Label(card, text="Log in to continue.", style="Muted.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", padx=18, pady=(0, 14))

        ttk.Label(card, text="Username", style="Body.TLabel").grid(row=2, column=0, sticky="w", padx=18, pady=(0, 6))
        username_entry = ttk.Entry(card, textvariable=self._username, width=34)
        username_entry.grid(row=3, column=0, columnspan=2, sticky="we", padx=18, pady=(0, 12))

        ttk.Label(card, text="Password", style="Body.TLabel").grid(row=4, column=0, sticky="w", padx=18, pady=(0, 6))
        pw_entry = ttk.Entry(card, textvariable=self._password, show="*", width=34)
        pw_entry.grid(row=5, column=0, columnspan=2, sticky="we", padx=18, pady=(0, 16))

        ttk.Button(card, text="Login", style="Primary.TButton", command=self._login).grid(row=6, column=0, columnspan=2, sticky="we", padx=18, pady=(0, 18))

        card.columnconfigure(0, weight=1)
        card.columnconfigure(1, weight=1)
        username_entry.focus_set()
        self._root.bind("<Return>", lambda _e: self._login())

    def _login(self) -> None:
        ops = OperationsService(self._conn)
        auth = AuthService(self._conn, ops.audit)
        try:
            with transaction(self._conn):
                user, session_id = auth.login(username=self._username.get().strip(), password=self._password.get(), device_id=self._device_id)
            perms = RBACService(self._conn).user_permissions(user.id)
        except Exception as exc:
            messagebox.showerror("Login Failed", str(exc), parent=self._root)
            return

        self._frame.destroy()
        MainWindow(root=self._root, conn=self._conn, user=user, session_id=session_id, device_id=self._device_id, permissions=perms).show()
