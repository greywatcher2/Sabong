from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import ttk

from cockpit.db.connection import transaction
from cockpit.services.audit import Actor, AuditService
from cockpit.ui.common import ask_text, show_error
from cockpit.utils.clock import utc_now


class FightStructuresView(tk.Frame):
    def __init__(self, *, parent: tk.Misc, conn: sqlite3.Connection, actor: Actor) -> None:
        bg = parent.cget("bg")
        super().__init__(parent, bg=bg)
        self._conn = conn
        self._actor = actor
        self._audit = AuditService(conn)

        ttk.Label(self, text="Fight Structures", style="ViewTitle.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))
        ttk.Button(self, text="Add/Update", style="Primary.TButton", command=self._upsert).grid(row=1, column=0, sticky="w")

        self._tree = ttk.Treeview(self, columns=("code", "name", "cocks", "rounds", "active"), show="headings", height=16)
        for col, title, w in (
            ("code", "Code", 110),
            ("name", "Name", 240),
            ("cocks", "Cocks/Entry", 110),
            ("rounds", "Default Rounds", 120),
            ("active", "Active", 70),
        ):
            self._tree.heading(col, text=title)
            self._tree.column(col, width=w, anchor="center")
        self._tree.grid(row=2, column=0, columnspan=3, sticky="nsew", pady=(10, 0))

        self.rowconfigure(2, weight=1)
        self.columnconfigure(2, weight=1)
        self._refresh()

    def _refresh(self) -> None:
        for i in self._tree.get_children():
            self._tree.delete(i)
        rows = self._conn.execute(
            "SELECT code, name, cocks_per_entry, default_rounds, is_active FROM fight_structures ORDER BY code"
        ).fetchall()
        for r in rows:
            self._tree.insert("", "end", text=r["code"], values=(r["code"], r["name"], r["cocks_per_entry"], r["default_rounds"], "YES" if int(r["is_active"]) else "NO"))

    def _upsert(self) -> None:
        code = ask_text(self, "Fight Structure", "Code (e.g., SINGLE, DERBY_2):")
        if not code:
            return
        name = ask_text(self, "Fight Structure", "Name:")
        if not name:
            return
        cocks_s = ask_text(self, "Fight Structure", "Cocks per entry:", initial="1")
        rounds_s = ask_text(self, "Fight Structure", "Default rounds:", initial="1")
        active_s = ask_text(self, "Fight Structure", "Active (YES/NO):", initial="YES") or "YES"
        try:
            cocks = int(cocks_s or "1")
            rounds = int(rounds_s or "1")
            active = 1 if active_s.strip().upper() in ("YES", "Y", "1", "TRUE") else 0
            prev = self._conn.execute(
                "SELECT code, name, cocks_per_entry, default_rounds, is_active FROM fight_structures WHERE code = ?",
                (code.strip().upper(),),
            ).fetchone()
            with transaction(self._conn):
                self._conn.execute(
                    """
                    INSERT INTO fight_structures(code, name, cocks_per_entry, default_rounds, is_active, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(code) DO UPDATE SET
                      name = excluded.name,
                      cocks_per_entry = excluded.cocks_per_entry,
                      default_rounds = excluded.default_rounds,
                      is_active = excluded.is_active
                    """,
                    (code.strip().upper(), name.strip(), cocks, rounds, active, utc_now().isoformat()),
                )
                self._audit.log(
                    actor=self._actor,
                    action="FIGHT_STRUCTURE_UPSERT",
                    entity_type="fight_structure",
                    entity_id=code.strip().upper(),
                    previous_state=dict(prev) if prev is not None else None,
                    new_state={"code": code.strip().upper(), "name": name.strip(), "cocks_per_entry": cocks, "default_rounds": rounds, "is_active": bool(active)},
                )
            self._refresh()
        except Exception as exc:
            show_error(self, "Fight Structure", exc)
