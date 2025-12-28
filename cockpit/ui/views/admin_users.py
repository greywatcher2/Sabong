from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import ttk

from cockpit.db.connection import transaction
from cockpit.services.audit import Actor
from cockpit.services.audit import AuditService
from cockpit.services.auth import AuthService
from cockpit.services.rbac import RBACService
from cockpit.ui.common import ask_text, show_error


class AdminUsersView(tk.Frame):
    def __init__(self, *, parent: tk.Misc, conn: sqlite3.Connection, actor: Actor) -> None:
        bg = parent.cget("bg")
        super().__init__(parent, bg=bg)
        self._conn = conn
        self._actor = actor
        self._audit = AuditService(conn)
        self._auth = AuthService(conn, self._audit)
        self._rbac = RBACService(conn)

        ttk.Label(self, text="User Management", style="ViewTitle.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))
        ttk.Button(self, text="Create User", style="Primary.TButton", command=self._create_user).grid(row=1, column=0, sticky="w")
        ttk.Button(self, text="Freeze/Unfreeze", style="Secondary.TButton", command=self._toggle_freeze).grid(row=1, column=1, sticky="w", padx=(10, 0))
        ttk.Button(self, text="Set Roles", style="Secondary.TButton", command=self._set_roles).grid(row=1, column=2, sticky="w", padx=(10, 0))

        self._tree = ttk.Treeview(self, columns=("username", "full_name", "frozen"), show="headings", height=14)
        for col, title, w in (("username", "Username", 160), ("full_name", "Full Name", 240), ("frozen", "Frozen", 80)):
            self._tree.heading(col, text=title)
            self._tree.column(col, width=w, anchor="center")
        self._tree.grid(row=2, column=0, columnspan=3, sticky="nsew", pady=(10, 0))
        self.rowconfigure(2, weight=1)
        self.columnconfigure(2, weight=1)

        self._refresh()

    def _refresh(self) -> None:
        for i in self._tree.get_children():
            self._tree.delete(i)
        rows = self._conn.execute("SELECT id, username, full_name, is_frozen FROM users ORDER BY username").fetchall()
        for r in rows:
            self._tree.insert("", "end", text=str(int(r["id"])), values=(r["username"], r["full_name"] or "", "YES" if int(r["is_frozen"]) else "NO"))

    def _selected_user_id(self) -> int | None:
        sel = self._tree.selection()
        if not sel:
            return None
        return int(self._tree.item(sel[0], "text"))

    def _create_user(self) -> None:
        username = ask_text(self, "Create User", "Username:")
        if not username:
            return
        full_name = ask_text(self, "Create User", "Full name (optional):", initial="") or None
        password = ask_text(self, "Create User", "Password:")
        if not password:
            return
        roles = self._conn.execute("SELECT name FROM roles ORDER BY name").fetchall()
        role_names = [r["name"] for r in roles if r["name"] != "Admin"]
        role = ask_text(self, "Create User", f"Role ({', '.join(role_names)}):", initial=role_names[0] if role_names else "Cashier")
        if not role:
            return
        try:
            with transaction(self._conn):
                self._auth.create_user(actor=self._actor, username=username.strip(), password=password, full_name=full_name, role_names=[role.strip()])
            self._refresh()
        except Exception as exc:
            show_error(self, "Create User", exc)

    def _toggle_freeze(self) -> None:
        user_id = self._selected_user_id()
        if user_id is None:
            return
        row = self._conn.execute("SELECT is_frozen FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            return
        frozen = bool(row["is_frozen"])
        reason = ask_text(self, "Freeze/Unfreeze", "Reason:", initial="") or ""
        try:
            with transaction(self._conn):
                self._auth.set_user_frozen(actor=self._actor, user_id=user_id, frozen=not frozen, reason=reason)
            self._refresh()
        except Exception as exc:
            show_error(self, "Freeze/Unfreeze", exc)

    def _set_roles(self) -> None:
        user_id = self._selected_user_id()
        if user_id is None:
            return

        role_rows = self._conn.execute("SELECT id, name FROM roles ORDER BY name").fetchall()
        roles = [(int(r["id"]), r["name"]) for r in role_rows]
        current = {
            int(r["role_id"])
            for r in self._conn.execute("SELECT role_id FROM user_roles WHERE user_id = ?", (user_id,)).fetchall()
        }

        win = tk.Toplevel(self)
        win.title("Set Roles")
        win.transient(self)
        win.grab_set()

        tk.Label(win, text=f"User ID: {user_id}", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=12, pady=(12, 6))
        box = tk.Listbox(win, selectmode="multiple", width=40, height=12)
        box.pack(fill="both", expand=True, padx=12, pady=6)

        for idx, (_rid, name) in enumerate(roles):
            box.insert("end", name)
            if _rid in current:
                box.selection_set(idx)

        def save() -> None:
            sel = set(box.curselection())
            selected_role_ids = [roles[i][0] for i in sel]
            try:
                prev_role_ids = [
                    int(r["role_id"])
                    for r in self._conn.execute("SELECT role_id FROM user_roles WHERE user_id = ? ORDER BY role_id", (user_id,)).fetchall()
                ]
                with transaction(self._conn):
                    self._conn.execute("DELETE FROM user_roles WHERE user_id = ?", (user_id,))
                    for rid in selected_role_ids:
                        self._conn.execute("INSERT INTO user_roles(user_id, role_id) VALUES(?, ?)", (user_id, rid))
                    self._audit.log(
                        actor=self._actor,
                        action="USER_ROLES_SET",
                        entity_type="user",
                        entity_id=str(user_id),
                        previous_state={"role_ids": prev_role_ids},
                        new_state={"role_ids": selected_role_ids},
                    )
                win.destroy()
            except Exception as exc:
                show_error(win, "Set Roles", exc)

        btns = tk.Frame(win)
        btns.pack(fill="x", padx=12, pady=(6, 12))
        ttk.Button(btns, text="Save", command=save).pack(side="right")
        ttk.Button(btns, text="Cancel", command=win.destroy).pack(side="right", padx=(0, 6))

        self.wait_window(win)
