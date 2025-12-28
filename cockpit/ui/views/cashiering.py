from __future__ import annotations

import os
import sqlite3
import tempfile
import tkinter as tk
from tkinter import ttk

from cockpit.db.connection import transaction
from cockpit.services.audit import Actor
from cockpit.services.audit import AuditService
from cockpit.services.betting import BettingService
from cockpit.services.operations import OperationsService
from cockpit.ui.common import ask_text, show_error
from cockpit.ui.common import palette
from cockpit.utils.qrcodegen import QrCode


class CashieringView(tk.Frame):
    def __init__(self, *, parent: tk.Misc, conn: sqlite3.Connection, actor: Actor, user_id: int, device_id: str) -> None:
        bg = parent.cget("bg")
        super().__init__(parent, bg=bg)
        self._conn = conn
        self._actor = actor
        self._user_id = user_id
        self._device_id = device_id
        self._ops = OperationsService(conn)
        self._betting = BettingService(conn, AuditService(conn))

        ttk.Label(self, text="Cashiering / Betting", style="ViewTitle.TLabel").grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 12))

        ttk.Label(self, text="Match", style="TLabel").grid(row=1, column=0, sticky="w", padx=(0, 10))
        self._match_combo = ttk.Combobox(self, state="readonly", width=30)
        self._match_combo.grid(row=1, column=1, sticky="w")
        ttk.Button(self, text="Refresh", style="Secondary.TButton", command=self._refresh_matches).grid(row=1, column=2, sticky="w", padx=(10, 0))

        ttk.Label(self, text="Side", style="TLabel").grid(row=2, column=0, sticky="w", pady=(10, 0), padx=(0, 10))
        self._side = ttk.Combobox(self, state="readonly", values=["WALA", "MERON", "DRAW"], width=10)
        self._side.grid(row=2, column=1, sticky="w", pady=(8, 0))
        self._side.set("WALA")

        ttk.Label(self, text="Amount (₱)", style="TLabel").grid(row=3, column=0, sticky="w", pady=(10, 0), padx=(0, 10))
        self._amount = tk.StringVar(value="10")
        amount_entry = ttk.Entry(self, textvariable=self._amount, width=14)
        amount_entry.grid(row=3, column=1, sticky="w", pady=(8, 0))

        ttk.Button(self, text="Encode + Print Slip", style="Primary.TButton", command=self._encode_and_print).grid(row=4, column=1, sticky="w", pady=(14, 0))

        ttk.Separator(self).grid(row=5, column=0, columnspan=4, sticky="ew", pady=14)

        ttk.Label(self, text="Payout (Scan QR text)", style="TLabel").grid(row=6, column=0, sticky="w", padx=(0, 10))
        self._qr = tk.StringVar()
        qr_entry = ttk.Entry(self, textvariable=self._qr, width=54)
        qr_entry.grid(row=6, column=1, columnspan=2, sticky="w")
        ttk.Button(self, text="Payout", style="Secondary.TButton", command=self._payout).grid(row=6, column=3, sticky="w", padx=(10, 0))

        p = palette()
        self._result = tk.Text(self, height=10, bg=p["surface"], fg=p["text"], highlightthickness=1, highlightbackground=p["border"], bd=0)
        self._result.grid(row=7, column=0, columnspan=4, sticky="nsew", pady=(10, 0))
        self.rowconfigure(7, weight=1)
        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=1)

        self._refresh_matches()

    def _refresh_matches(self) -> None:
        rows = self._conn.execute(
            "SELECT id, match_number, state FROM fight_matches WHERE state IN ('DRAFT','LOCKED','ACTIVE') ORDER BY id DESC LIMIT 30"
        ).fetchall()
        options = [f"{r['id']} | {r['match_number']} | {r['state']}" for r in rows]
        self._match_combo["values"] = options
        if options and not self._match_combo.get():
            self._match_combo.set(options[0])

    def _selected_match_id(self) -> int:
        value = self._match_combo.get()
        if not value:
            raise ValueError("Select a match")
        return int(value.split("|", 1)[0].strip())

    def _encode_and_print(self) -> None:
        try:
            match_id = self._selected_match_id()
            side = self._side.get()
            amount = int(self._amount.get())
            with transaction(self._conn):
                slip = self._ops.encode_bet_with_cash(
                    actor=self._actor,
                    cashier_user_id=self._user_id,
                    device_id=self._device_id,
                    match_id=match_id,
                    side=side,
                    amount=amount,
                )
                self._betting.mark_printed(actor=self._actor, bet_id=int(slip["id"]))
            self._print_slip(slip_number=slip["slip_number"], qr_payload=slip["qr_payload"], match_id=match_id, side=side, amount=amount)
            self._append(f"ENCODED: {slip['slip_number']} | QR={slip['qr_payload']}\n")
        except Exception as exc:
            show_error(self, "Encode Bet", exc)

    def _print_slip(self, *, slip_number: str, qr_payload: str, match_id: int, side: str, amount: int) -> None:
        match = self._conn.execute("SELECT match_number FROM fight_matches WHERE id = ?", (match_id,)).fetchone()
        match_no = match["match_number"] if match else str(match_id)
        qr = QrCode.encode_text(qr_payload, QrCode.Ecc.MEDIUM)
        border = 2
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" viewBox="0 0 {qr.get_size()+border*2} {qr.get_size()+border*2}" stroke="none">'
            f'<rect width="100%" height="100%" fill="#FFFFFF"/>'
            f'<path d="'
        )
        for y in range(qr.get_size()):
            for x in range(qr.get_size()):
                if qr.get_module(x, y):
                    svg += f"M{x+border},{y+border}h1v1h-1z "
        svg += f'" fill="#000000"/></svg>'

        html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Bet Slip {slip_number}</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; }}
    .slip {{ width: 320px; }}
    .title {{ font-size: 18px; font-weight: 700; margin-bottom: 8px; }}
    .row {{ font-size: 14px; margin: 2px 0; }}
    .qr {{ margin-top: 10px; }}
    .qr svg {{ width: 220px; height: 220px; }}
    .payload {{ font-family: Consolas, monospace; font-size: 12px; word-break: break-all; }}
  </style>
</head>
<body>
  <div class="slip">
    <div class="title">COCKFIGHT BET SLIP</div>
    <div class="row">Slip #: {slip_number}</div>
    <div class="row">Match #: {match_no}</div>
    <div class="row">Side: {side}</div>
    <div class="row">Amount: ₱{amount}</div>
    <div class="qr">{svg}</div>
    <div class="row">QR Payload:</div>
    <div class="payload">{qr_payload}</div>
  </div>
</body>
</html>
"""

        fd, path = tempfile.mkstemp(prefix="bet_slip_", suffix=".html")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        try:
            os.startfile(path, "print")
        except Exception:
            os.startfile(path)

    def _payout(self) -> None:
        qr = self._qr.get().strip()
        if not qr:
            return
        try:
            with transaction(self._conn):
                result = self._ops.payout_bet_with_cash(actor=self._actor, cashier_user_id=self._user_id, qr_payload=qr)
            self._append(f"PAID: {result['slip_number']} | payout=₱{result['payout_amount']}\n")
            self._qr.set("")
        except Exception as exc:
            show_error(self, "Payout", exc)

    def _append(self, text: str) -> None:
        self._result.insert("end", text)
        self._result.see("end")

