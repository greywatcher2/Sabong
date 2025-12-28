from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
from tkinter import ttk

from cockpit.db.connection import transaction
from cockpit.services.audit import Actor
from cockpit.services.auth import AuthService
from cockpit.services.operations import OperationsService
from cockpit.ui.common import palette
from cockpit.utils.device import get_device_id


class SetupAdminWindow:
    def __init__(self, *, root: tk.Tk, ops: OperationsService) -> None:
        self._root = root
        self._ops = ops
        self._device_id = get_device_id()

        bg = root.cget("bg")
        self._frame = tk.Frame(root, bg=bg)
        self._shell = tk.Frame(self._frame, bg=bg)
        self._username = tk.StringVar(value="admin")
        self._full_name = tk.StringVar(value="Administrator")
        self._password = tk.StringVar(value="")
        self._password2 = tk.StringVar(value="")

    def show(self) -> None:
        self._root.protocol("WM_DELETE_WINDOW", self._root.destroy)
        self._frame.pack(fill="both", expand=True)
        self._shell.place(relx=0.5, rely=0.5, anchor="center")

        p = palette()
        card_outer = tk.Frame(self._shell, bg=p["shadow"])
        card_outer.pack()
        card = tk.Frame(card_outer, bg=p["surface"])
        card.pack(padx=1, pady=1)

        ttk.Label(card, text="First-time setup", style="Title.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", padx=18, pady=(18, 6))
        ttk.Label(card, text="Create the first Admin user.", style="Muted.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", padx=18, pady=(0, 14))

        ttk.Label(card, text="Username", style="Body.TLabel").grid(row=2, column=0, sticky="w", padx=18, pady=(0, 6))
        ttk.Entry(card, textvariable=self._username, width=34).grid(row=3, column=0, columnspan=2, sticky="we", padx=18, pady=(0, 12))

        ttk.Label(card, text="Full name", style="Body.TLabel").grid(row=4, column=0, sticky="w", padx=18, pady=(0, 6))
        ttk.Entry(card, textvariable=self._full_name, width=34).grid(row=5, column=0, columnspan=2, sticky="we", padx=18, pady=(0, 12))

        ttk.Label(card, text="Password", style="Body.TLabel").grid(row=6, column=0, sticky="w", padx=18, pady=(0, 6))
        ttk.Entry(card, textvariable=self._password, show="*", width=34).grid(row=7, column=0, columnspan=2, sticky="we", padx=18, pady=(0, 12))

        ttk.Label(card, text="Confirm password", style="Body.TLabel").grid(row=8, column=0, sticky="w", padx=18, pady=(0, 6))
        ttk.Entry(card, textvariable=self._password2, show="*", width=34).grid(row=9, column=0, columnspan=2, sticky="we", padx=18, pady=(0, 16))

        ttk.Button(card, text="Create Admin", style="Primary.TButton", command=self._create).grid(row=10, column=0, columnspan=2, sticky="we", padx=18, pady=(0, 18))

        card.columnconfigure(0, weight=1)
        card.columnconfigure(1, weight=1)

    def _create(self) -> None:
        username = self._username.get().strip()
        full_name = self._full_name.get().strip() or None
        password = self._password.get()
        password2 = self._password2.get()
        if not username:
            messagebox.showerror("Setup", "Username is required", parent=self._root)
            return
        if not password:
            messagebox.showerror("Setup", "Password is required", parent=self._root)
            return
        if password != password2:
            messagebox.showerror("Setup", "Passwords do not match", parent=self._root)
            return

        actor = Actor(user_id=None, device_id=self._device_id)
        auth = AuthService(self._ops._conn, self._ops.audit)
        with transaction(self._ops._conn):
            auth.create_user(actor=actor, username=username, password=password, full_name=full_name, role_names=["Admin"])
        messagebox.showinfo("Setup", "Admin user created. Restarting to login screen.", parent=self._root)
        self._frame.destroy()
        from cockpit.ui.shell import ShellWindow

        ShellWindow(root=self._root, conn=self._ops._conn).show()
