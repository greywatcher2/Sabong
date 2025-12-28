from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import ttk

from cockpit.db.connection import transaction
from cockpit.services.audit import Actor, AuditService
from cockpit.ui.common import ask_text, palette, show_error


class RoleManagementView(tk.Frame):
    def __init__(self, *, parent: tk.Misc, conn: sqlite3.Connection, actor: Actor) -> None:
        bg = parent.cget("bg")
        super().__init__(parent, bg=bg)
        self._conn = conn
        self._actor = actor
        self._audit = AuditService(conn)

        ttk.Label(self, text="Roles & Permissions", style="ViewTitle.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))

        ttk.Button(self, text="Create Role", style="Secondary.TButton", command=self._create_role).grid(row=1, column=0, sticky="w")

        self._roles = ttk.Treeview(self, columns=("name",), show="headings", height=14)
        self._roles.heading("name", text="Role")
        self._roles.column("name", width=220, anchor="w")
        self._roles.grid(row=2, column=0, sticky="nsew", padx=(0, 10), pady=(10, 0))
        self._roles.bind("<<TreeviewSelect>>", lambda _e: self._refresh_perms())

        self._perm_frame = ttk.LabelFrame(self, text="Permissions", padding=(12, 12))
        self._perm_frame.grid(row=2, column=1, columnspan=2, sticky="nsew", pady=(10, 0))

        self._perm_vars: dict[int, tk.BooleanVar] = {}
        self._perm_checkbuttons: list[tk.Checkbutton] = []
        ttk.Button(self._perm_frame, text="Save", style="Primary.TButton", command=self._save).grid(row=0, column=0, sticky="e", pady=(0, 10))

        self.columnconfigure(1, weight=1)
        self.rowconfigure(2, weight=1)

        self._refresh_roles()

    def _refresh_roles(self) -> None:
        for i in self._roles.get_children():
            self._roles.delete(i)
        rows = self._conn.execute("SELECT id, name FROM roles ORDER BY name").fetchall()
        for r in rows:
            self._roles.insert("", "end", text=str(int(r["id"])), values=(r["name"],))
        self._refresh_perms()

    def _selected_role_id(self) -> int | None:
        sel = self._roles.selection()
        if not sel:
            return None
        return int(self._roles.item(sel[0], "text"))

    def _create_role(self) -> None:
        name = ask_text(self, "Create Role", "Role name:")
        if not name:
            return
        try:
            with transaction(self._conn):
                cur = self._conn.execute("INSERT INTO roles(name, description) VALUES(?, NULL)", (name.strip(),))
                role_id = int(cur.lastrowid)
                self._audit.log(actor=self._actor, action="ROLE_CREATE", entity_type="role", entity_id=str(role_id), new_state={"name": name.strip()})
            self._refresh_roles()
        except Exception as exc:
            show_error(self, "Create Role", exc)

    def _refresh_perms(self) -> None:
        for cb in self._perm_checkbuttons:
            cb.destroy()
        self._perm_checkbuttons.clear()
        self._perm_vars.clear()

        role_id = self._selected_role_id()
        if role_id is None:
            return

        perms = self._conn.execute("SELECT id, code, description FROM permissions ORDER BY code").fetchall()
        assigned = {
            int(r["permission_id"])
            for r in self._conn.execute("SELECT permission_id FROM role_permissions WHERE role_id = ?", (role_id,)).fetchall()
        }

        pal = palette()
        r = 1
        for p in perms:
            var = tk.BooleanVar(value=int(p["id"]) in assigned)
            self._perm_vars[int(p["id"])] = var
            text = f"{p['code']} - {p['description'] or ''}"
            cb = tk.Checkbutton(
                self._perm_frame,
                text=text,
                variable=var,
                anchor="w",
                justify="left",
                wraplength=520,
                bg=pal["bg"],
                fg=pal["text"],
                activebackground=pal["select_bg"],
                activeforeground=pal["text"],
                selectcolor=pal["surface"],
                highlightthickness=0,
                bd=0,
            )
            cb.grid(row=r, column=0, sticky="w", pady=2)
            self._perm_checkbuttons.append(cb)
            r += 1

        self._perm_frame.columnconfigure(0, weight=1)

    def _save(self) -> None:
        role_id = self._selected_role_id()
        if role_id is None:
            return
        try:
            prev_perm_codes = [
                r["code"]
                for r in self._conn.execute(
                    """
                    SELECT p.code
                    FROM permissions p
                    JOIN role_permissions rp ON rp.permission_id = p.id
                    WHERE rp.role_id = ?
                    ORDER BY p.code
                    """,
                    (role_id,),
                ).fetchall()
            ]
            selected_perm_ids = [perm_id for perm_id, var in self._perm_vars.items() if var.get()]
            new_perm_codes = [
                r["code"]
                for r in self._conn.execute(
                    "SELECT code FROM permissions WHERE id IN (%s) ORDER BY code" % ",".join("?" for _ in selected_perm_ids),
                    tuple(selected_perm_ids),
                ).fetchall()
            ] if selected_perm_ids else []
            with transaction(self._conn):
                self._conn.execute("DELETE FROM role_permissions WHERE role_id = ?", (role_id,))
                for perm_id, var in self._perm_vars.items():
                    if var.get():
                        self._conn.execute(
                            "INSERT INTO role_permissions(role_id, permission_id) VALUES(?, ?)",
                            (role_id, perm_id),
                        )
                self._audit.log(
                    actor=self._actor,
                    action="ROLE_PERMS_SET",
                    entity_type="role",
                    entity_id=str(role_id),
                    previous_state={"permission_codes": prev_perm_codes},
                    new_state={"permission_codes": new_perm_codes},
                )
        except Exception as exc:
            show_error(self, "Save Role", exc)
