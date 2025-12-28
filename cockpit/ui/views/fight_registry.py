from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import ttk

from cockpit.db.connection import transaction
from cockpit.services.audit import Actor
from cockpit.services.audit import AuditService
from cockpit.services.fight import FightService
from cockpit.ui.common import ask_text, show_error


class FightRegistryView(tk.Frame):
    def __init__(self, *, parent: tk.Misc, conn: sqlite3.Connection, actor: Actor, permissions: set[str]) -> None:
        bg = parent.cget("bg")
        super().__init__(parent, bg=bg)
        self._conn = conn
        self._actor = actor
        self._perms = permissions
        self._svc = FightService(conn, AuditService(conn))

        ttk.Label(self, text="Fight Registry", style="ViewTitle.TLabel").grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 12))

        self._match_tree = ttk.Treeview(self, columns=("match", "structure", "rounds", "state", "locked"), show="headings", height=10)
        for col, title, w in (
            ("match", "Match #", 120),
            ("structure", "Structure", 140),
            ("rounds", "Rounds", 80),
            ("state", "State", 100),
            ("locked", "Locked At", 180),
        ):
            self._match_tree.heading(col, text=title)
            self._match_tree.column(col, width=w, anchor="center")
        self._match_tree.grid(row=1, column=0, columnspan=4, sticky="nsew")

        ttk.Button(self, text="New Match", style="Primary.TButton", command=self._new_match).grid(row=2, column=0, sticky="w", pady=(12, 0))
        ttk.Button(self, text="Add Entry", style="Secondary.TButton", command=self._add_entry).grid(row=2, column=1, sticky="w", pady=(12, 0), padx=(10, 0))
        if "FIGHT_CONTROL" in self._perms:
            ttk.Button(self, text="Start", style="Secondary.TButton", command=self._start).grid(row=2, column=2, sticky="w", pady=(12, 0), padx=(10, 0))
            ttk.Button(self, text="Stop", style="Secondary.TButton", command=self._stop).grid(row=2, column=3, sticky="w", pady=(12, 0), padx=(10, 0))
        if "FIGHT_CANCEL_PRELOCK" in self._perms:
            ttk.Button(self, text="Cancel Match (Pre-Lock)", style="Secondary.TButton", command=self._cancel_match_prelock).grid(row=4, column=1, sticky="w", pady=(12, 0))
        if "FIGHT_OVERRIDE" in self._perms:
            ttk.Button(self, text="Void Match (Override)", style="Secondary.TButton", command=self._void_match).grid(row=4, column=3, sticky="w", pady=(12, 0))

        self._entry_tree = ttk.Treeview(self, columns=("side", "name", "owner", "cocks", "weight", "color"), show="headings", height=10)
        for col, title, w in (
            ("side", "Side", 70),
            ("name", "Entry Name", 200),
            ("owner", "Owner", 160),
            ("cocks", "# Cocks", 80),
            ("weight", "Weight/Cock", 110),
            ("color", "Color", 90),
        ):
            self._entry_tree.heading(col, text=title)
            self._entry_tree.column(col, width=w, anchor="center")
        self._entry_tree.grid(row=3, column=0, columnspan=4, sticky="nsew", pady=(10, 0))

        if "FIGHT_RESULT_SET" in self._perms:
            ttk.Button(self, text="Set Result", style="Primary.TButton", command=self._set_result).grid(row=4, column=0, sticky="w", pady=(12, 0))
        if "FIGHT_CANCEL_PRELOCK" in self._perms:
            ttk.Button(self, text="Cancel Entry (Pre-Lock)", style="Secondary.TButton", command=self._cancel_entry_prelock).grid(row=4, column=2, sticky="w", pady=(12, 0))
        if "FIGHT_OVERRIDE" in self._perms:
            ttk.Button(self, text="Override Result", style="Secondary.TButton", command=self._override_result).grid(row=4, column=3, sticky="e", pady=(12, 0))

        self._match_tree.bind("<<TreeviewSelect>>", lambda _e: self._refresh_entries())

        for c in range(4):
            self.columnconfigure(c, weight=1)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(3, weight=1)

        self._refresh_matches()

    def _selected_match_id(self) -> int | None:
        sel = self._match_tree.selection()
        if not sel:
            return None
        return int(self._match_tree.item(sel[0], "text"))

    def _refresh_matches(self) -> None:
        for i in self._match_tree.get_children():
            self._match_tree.delete(i)
        rows = self._conn.execute(
            "SELECT id, match_number, structure_code, rounds, state, locked_at FROM fight_matches ORDER BY id DESC LIMIT 50"
        ).fetchall()
        for r in rows:
            self._match_tree.insert(
                "",
                "end",
                text=str(int(r["id"])),
                values=(r["match_number"], r["structure_code"], r["rounds"], r["state"], r["locked_at"] or ""),
            )
        self._refresh_entries()

    def _refresh_entries(self) -> None:
        for i in self._entry_tree.get_children():
            self._entry_tree.delete(i)
        match_id = self._selected_match_id()
        if match_id is None:
            return
        rows = self._conn.execute(
            """
            SELECT id, side, entry_name, owner, num_cocks, weight_per_cock, color
            FROM fight_entries
            WHERE match_id = ? AND deleted_at IS NULL
            ORDER BY side, id
            """,
            (match_id,),
        ).fetchall()
        for r in rows:
            self._entry_tree.insert(
                "",
                "end",
                text=str(int(r["id"])),
                values=(r["side"], r["entry_name"], r["owner"], r["num_cocks"], r["weight_per_cock"], r["color"]),
            )

    def _new_match(self) -> None:
        match_number = ask_text(self, "New Match", "Match number (unique):")
        if not match_number:
            return
        structures = self._conn.execute("SELECT code FROM fight_structures WHERE is_active = 1 ORDER BY code").fetchall()
        codes = [r["code"] for r in structures] if structures else ["SINGLE"]
        structure = ask_text(self, "New Match", f"Structure code ({', '.join(codes)}):", initial=codes[0]) or codes[0]
        rounds_s = ask_text(self, "New Match", "Rounds (integer >=1):", initial="1") or "1"
        try:
            rounds = int(rounds_s)
            with transaction(self._conn):
                self._svc.create_match(actor=self._actor, match_number=match_number, structure_code=structure, rounds=rounds, created_by=self._actor.user_id or 0)
            self._refresh_matches()
        except Exception as exc:
            show_error(self, "New Match", exc)

    def _add_entry(self) -> None:
        match_id = self._selected_match_id()
        if match_id is None:
            show_error(self, "Add Entry", "Select a match first")
            return
        side = ask_text(self, "Add Entry", "Side (WALA or MERON):", initial="WALA")
        if not side:
            return
        entry_name = ask_text(self, "Add Entry", "Entry name:")
        owner = ask_text(self, "Add Entry", "Owner:")
        num_cocks_s = ask_text(self, "Add Entry", "Number of cocks:", initial="1")
        weight_s = ask_text(self, "Add Entry", "Weight per cock:", initial="2.0")
        color = ask_text(self, "Add Entry", "Color:", initial="RED")
        if not all([entry_name, owner, num_cocks_s, weight_s, color]):
            return
        try:
            with transaction(self._conn):
                self._svc.add_entry(
                    actor=self._actor,
                    match_id=match_id,
                    side=side.strip().upper(),
                    entry_name=entry_name.strip(),
                    owner=owner.strip(),
                    num_cocks=int(num_cocks_s),
                    weight_per_cock=float(weight_s),
                    color=color.strip().upper(),
                )
            self._refresh_entries()
        except Exception as exc:
            show_error(self, "Add Entry", exc)

    def _start(self) -> None:
        match_id = self._selected_match_id()
        if match_id is None:
            return
        try:
            with transaction(self._conn):
                self._svc.start_match(actor=self._actor, match_id=match_id)
            self._refresh_matches()
        except Exception as exc:
            show_error(self, "Start Match", exc)

    def _stop(self) -> None:
        match_id = self._selected_match_id()
        if match_id is None:
            return
        try:
            with transaction(self._conn):
                self._svc.stop_match(actor=self._actor, match_id=match_id)
            self._refresh_matches()
        except Exception as exc:
            show_error(self, "Stop Match", exc)

    def _set_result(self) -> None:
        match_id = self._selected_match_id()
        if match_id is None:
            return
        result = ask_text(self, "Set Result", "Result (WALA/MERON/DRAW/CANCELLED/NO_CONTEST):", initial="WALA")
        if not result:
            return
        notes = ask_text(self, "Set Result", "Notes (optional):", initial="") or None
        try:
            with transaction(self._conn):
                self._svc.set_result(actor=self._actor, match_id=match_id, result_type=result.strip().upper(), decided_by=self._actor.user_id or 0, notes=notes)
            self._refresh_matches()
        except Exception as exc:
            show_error(self, "Set Result", exc)

    def _override_result(self) -> None:
        match_id = self._selected_match_id()
        if match_id is None:
            return
        result = ask_text(self, "Override Result", "Result (WALA/MERON/DRAW/CANCELLED/NO_CONTEST):", initial="WALA")
        if not result:
            return
        notes = ask_text(self, "Override Result", "Notes (required):", initial="") or ""
        try:
            with transaction(self._conn):
                self._svc.set_result(
                    actor=self._actor,
                    match_id=match_id,
                    result_type=result.strip().upper(),
                    decided_by=self._actor.user_id or 0,
                    notes=notes,
                    override=True,
                )
            self._refresh_matches()
        except Exception as exc:
            show_error(self, "Override Result", exc)

    def _selected_entry_id(self) -> int | None:
        sel = self._entry_tree.selection()
        if not sel:
            return None
        return int(self._entry_tree.item(sel[0], "text"))

    def _cancel_entry_prelock(self) -> None:
        match_id = self._selected_match_id()
        if match_id is None:
            return
        entry_id = self._selected_entry_id()
        if entry_id is None:
            show_error(self, "Cancel Entry", "Select an entry first")
            return
        reason = ask_text(self, "Cancel Entry", "Reason:", initial="") or ""
        try:
            with transaction(self._conn):
                self._svc.cancel_entry_prelock(actor=self._actor, entry_id=entry_id, reason=reason)
            self._refresh_entries()
        except Exception as exc:
            show_error(self, "Cancel Entry", exc)

    def _cancel_match_prelock(self) -> None:
        match_id = self._selected_match_id()
        if match_id is None:
            return
        reason = ask_text(self, "Cancel Match", "Reason:", initial="") or ""
        try:
            with transaction(self._conn):
                self._svc.cancel_match_prelock(actor=self._actor, match_id=match_id, reason=reason)
            self._refresh_matches()
        except Exception as exc:
            show_error(self, "Cancel Match", exc)

    def _void_match(self) -> None:
        match_id = self._selected_match_id()
        if match_id is None:
            return
        reason = ask_text(self, "Void Match", "Reason (required):", initial="") or ""
        if not reason.strip():
            show_error(self, "Void Match", "Reason is required")
            return
        try:
            with transaction(self._conn):
                self._svc.void_match(actor=self._actor, match_id=match_id, reason=reason.strip())
            self._refresh_matches()
        except Exception as exc:
            show_error(self, "Void Match", exc)

