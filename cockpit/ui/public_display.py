from __future__ import annotations

import sqlite3
import tkinter as tk

from cockpit.services.betting import BettingService


class PublicDisplayWindow:
    def __init__(self, *, root: tk.Tk, conn: sqlite3.Connection) -> None:
        self._root = root
        self._conn = conn
        self._betting = BettingService(conn, audit=None)

        self._frame = tk.Frame(root, padx=18, pady=18, bg="black")
        self._title = tk.Label(self._frame, text="PUBLIC DISPLAY", fg="white", bg="black", font=("Segoe UI", 24, "bold"))
        self._active = tk.Label(self._frame, text="", fg="white", bg="black", font=("Segoe UI", 20, "bold"))
        self._odds = tk.Label(self._frame, text="", fg="white", bg="black", font=("Consolas", 16))
        self._history = tk.Text(self._frame, height=12, width=80, bg="black", fg="white", font=("Consolas", 14), bd=0)

    def show(self) -> None:
        self._root.protocol("WM_DELETE_WINDOW", self._root.destroy)
        self._root.attributes("-fullscreen", True)
        self._frame.pack(fill="both", expand=True)
        self._title.pack(anchor="w", pady=(0, 18))
        self._active.pack(anchor="w", pady=(0, 10))
        self._odds.pack(anchor="w", pady=(0, 14))
        self._history.pack(fill="both", expand=True)
        self._history.configure(state="disabled")
        self._frame.bind_all("<Escape>", lambda _e: self._root.destroy())
        self._refresh()

    def _refresh(self) -> None:
        match = self._conn.execute(
            """
            SELECT id, match_number, COALESCE(fight_number, id) AS fight_number, state
            FROM fight_matches
            WHERE state IN ('LOCKED','ACTIVE','DRAFT')
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

        if match is None:
            self._active.configure(text="No active matches")
            self._odds.configure(text="")
        else:
            entries = self._conn.execute(
                """
                SELECT side, entry_name
                FROM fight_entries
                WHERE match_id = ? AND deleted_at IS NULL
                ORDER BY side, id
                """,
                (int(match["id"]),),
            ).fetchall()
            wala = ", ".join([e["entry_name"] for e in entries if e["side"] == "WALA"]) or "-"
            meron = ", ".join([e["entry_name"] for e in entries if e["side"] == "MERON"]) or "-"
            odds = self._betting.get_odds(int(match["id"]))
            self._active.configure(text=f"Match {match['match_number']}  |  Fight {match['fight_number']}  |  {wala} vs {meron}  |  State: {match['state']}")
            self._odds.configure(
                text=(
                    f"WALA ₱{odds.total_wala:<6}  "
                    f"MERON ₱{odds.total_meron:<6}  "
                    f"DRAW ₱{odds.total_draw:<6}  "
                    f"TOTAL ₱{odds.total_all:<6}\n"
                    f"WALA MULT: {odds.wala_multiplier or 0:.2f}   "
                    f"MERON MULT: {odds.meron_multiplier or 0:.2f}   "
                    f"DRAW MULT: 5.00"
                )
            )

        rows = self._conn.execute(
            """
            SELECT fm.match_number, fr.result_type, fr.decided_at
            FROM fight_results fr
            JOIN fight_matches fm ON fm.id = fr.match_id
            ORDER BY fr.decided_at DESC
            LIMIT 10
            """
        ).fetchall()
        self._history.configure(state="normal")
        self._history.delete("1.0", "end")
        self._history.insert("end", "RECENT MATCH HISTORY\n\n")
        for r in rows:
            self._history.insert("end", f"{r['decided_at']}  |  Match {r['match_number']}  |  Result: {r['result_type']}\n")
        self._history.configure(state="disabled")

        self._root.after(1000, self._refresh)

