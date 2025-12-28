from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import ttk

from cockpit.ui.common import palette


class DashboardView(tk.Frame):
    def __init__(self, *, parent: tk.Misc, conn: sqlite3.Connection) -> None:
        bg = parent.cget("bg")
        super().__init__(parent, bg=bg)
        self._conn = conn

        ttk.Label(self, text="Monitoring Dashboard", style="ViewTitle.TLabel").pack(anchor="w", pady=(0, 12))

        self._tree = ttk.Treeview(self, columns=("match", "state", "wala", "meron", "draw", "total"), show="headings", height=14)
        for col, title, w in (
            ("match", "Match #", 120),
            ("state", "State", 100),
            ("wala", "Wala Bets", 100),
            ("meron", "Meron Bets", 110),
            ("draw", "Draw Bets", 100),
            ("total", "Total", 100),
        ):
            self._tree.heading(col, text=title)
            self._tree.column(col, width=w, anchor="center")
        self._tree.pack(fill="both", expand=True)

        p = palette()
        self._cash = tk.Text(self, height=6, bg=p["surface"], fg=p["text"], highlightthickness=1, highlightbackground=p["border"], bd=0)
        self._cash.pack(fill="x", pady=(10, 0))
        self._cash.configure(state="disabled")

        self._refresh()

    def _refresh(self) -> None:
        for i in self._tree.get_children():
            self._tree.delete(i)
        rows = self._conn.execute(
            """
            SELECT
              fm.id,
              fm.match_number,
              fm.state,
              COALESCE(v.total_wala, 0) AS total_wala,
              COALESCE(v.total_meron, 0) AS total_meron,
              COALESCE(v.total_draw, 0) AS total_draw,
              COALESCE(v.total_all, 0) AS total_all
            FROM fight_matches fm
            LEFT JOIN vw_bet_totals v ON v.match_id = fm.id
            WHERE fm.state IN ('DRAFT','LOCKED','ACTIVE')
            ORDER BY fm.id DESC
            LIMIT 20
            """
        ).fetchall()
        for r in rows:
            self._tree.insert(
                "",
                "end",
                values=(r["match_number"], r["state"], f"₱{int(r['total_wala'])}", f"₱{int(r['total_meron'])}", f"₱{int(r['total_draw'])}", f"₱{int(r['total_all'])}"),
            )

        cash_rows = self._conn.execute(
            """
            SELECT drawer_type, name, owner_user_id, current_cash
            FROM cash_drawers
            WHERE closed_at IS NULL
            ORDER BY drawer_type, name
            """
        ).fetchall()
        self._cash.configure(state="normal")
        self._cash.delete("1.0", "end")
        self._cash.insert("end", "Cash On Hand (Open Drawers)\n")
        for r in cash_rows:
            self._cash.insert("end", f"- {r['drawer_type']} | {r['name']} | owner={r['owner_user_id']} | ₱{int(r['current_cash'])}\n")
        self._cash.configure(state="disabled")

        self.after(1000, self._refresh)
