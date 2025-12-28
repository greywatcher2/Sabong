from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import ttk

from cockpit.ui.common import palette


class AuditLogView(tk.Frame):
    def __init__(self, *, parent: tk.Misc, conn: sqlite3.Connection) -> None:
        bg = parent.cget("bg")
        super().__init__(parent, bg=bg)
        self._conn = conn

        ttk.Label(self, text="Immutable Audit Log", style="ViewTitle.TLabel").pack(anchor="w", pady=(0, 12))

        self._tree = ttk.Treeview(
            self,
            columns=("ts", "actor", "action", "entity", "entity_id"),
            show="headings",
            height=18,
        )
        for col, title, w in (
            ("ts", "Timestamp", 190),
            ("actor", "Actor User", 110),
            ("action", "Action", 190),
            ("entity", "Entity", 140),
            ("entity_id", "Entity ID", 110),
        ):
            self._tree.heading(col, text=title)
            self._tree.column(col, width=w, anchor="center")
        self._tree.pack(fill="both", expand=True)

        p = palette()
        self._details = tk.Text(self, height=10, bg=p["surface"], fg=p["text"], highlightthickness=1, highlightbackground=p["border"], bd=0)
        self._details.pack(fill="x", pady=(10, 0))
        self._details.configure(state="disabled")

        self._tree.bind("<<TreeviewSelect>>", lambda _e: self._show_details())
        self._refresh()

    def _refresh(self) -> None:
        for i in self._tree.get_children():
            self._tree.delete(i)
        rows = self._conn.execute(
            """
            SELECT id, actor_user_id, actor_device_id, action, entity_type, entity_id, created_at
            FROM audit_log
            ORDER BY id DESC
            LIMIT 500
            """
        ).fetchall()
        for r in rows:
            self._tree.insert(
                "",
                "end",
                text=str(int(r["id"])),
                values=(
                    r["created_at"],
                    str(r["actor_user_id"]) if r["actor_user_id"] is not None else "SYSTEM",
                    r["action"],
                    r["entity_type"],
                    r["entity_id"] or "",
                ),
            )

    def _show_details(self) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        log_id = int(self._tree.item(sel[0], "text"))
        row = self._conn.execute(
            """
            SELECT previous_state_json, new_state_json, metadata_json
            FROM audit_log
            WHERE id = ?
            """,
            (log_id,),
        ).fetchone()
        if row is None:
            return
        self._details.configure(state="normal")
        self._details.delete("1.0", "end")
        self._details.insert("end", "PREVIOUS:\n")
        self._details.insert("end", (row["previous_state_json"] or "") + "\n\n")
        self._details.insert("end", "NEW:\n")
        self._details.insert("end", (row["new_state_json"] or "") + "\n\n")
        self._details.insert("end", "METADATA:\n")
        self._details.insert("end", (row["metadata_json"] or "") + "\n")
        self._details.configure(state="disabled")

