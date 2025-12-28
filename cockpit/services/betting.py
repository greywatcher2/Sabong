from __future__ import annotations

import json
import math
import secrets
import sqlite3
from dataclasses import dataclass
from typing import Any

from cockpit.services.audit import Actor, AuditService
from cockpit.services.errors import ValidationError
from cockpit.utils.clock import utc_now


@dataclass(frozen=True)
class Odds:
    total_wala: int
    total_meron: int
    total_draw: int
    total_all: int
    wala_multiplier: float | None
    meron_multiplier: float | None


class BettingService:
    """
    Betting, payout, and accounting.

    Result logic:
    - If WALA or MERON wins: DRAW bettors lose.
    - If DRAW: DRAW bettors receive 5× bet; WALA & MERON are refunded.
    - If CANCELLED / NO_CONTEST: all bettors refunded.
    """

    def __init__(self, conn: sqlite3.Connection, audit: AuditService | None) -> None:
        self._conn = conn
        self._audit = audit

    def get_odds(self, match_id: int) -> Odds:
        totals = self._conn.execute(
            "SELECT total_wala, total_meron, total_draw, total_all FROM vw_bet_totals WHERE match_id = ?",
            (match_id,),
        ).fetchone()
        if totals is None:
            tw = tm = td = ta = 0
        else:
            tw = int(totals["total_wala"] or 0)
            tm = int(totals["total_meron"] or 0)
            td = int(totals["total_draw"] or 0)
            ta = int(totals["total_all"] or 0)

        wala_mult = (ta / tw) if tw > 0 else None
        meron_mult = (ta / tm) if tm > 0 else None
        return Odds(
            total_wala=tw,
            total_meron=tm,
            total_draw=td,
            total_all=ta,
            wala_multiplier=wala_mult,
            meron_multiplier=meron_mult,
        )

    def _new_slip_number(self) -> str:
        token = secrets.token_hex(4).upper()
        return f"S{utc_now().strftime('%Y%m%d')}-{token}"

    def _new_qr_payload(self) -> str:
        return secrets.token_urlsafe(16)

    def encode_bet(
        self,
        *,
        actor: Actor,
        encoded_by: int,
        device_id: str,
        match_id: int,
        side: str,
        amount: int,
    ) -> dict[str, Any]:
        if side not in ("WALA", "MERON", "DRAW"):
            raise ValidationError("Side must be WALA, MERON, or DRAW")
        if amount < 10:
            raise ValidationError("Minimum bet is ₱10")

        match = self._conn.execute("SELECT id, state FROM fight_matches WHERE id = ?", (match_id,)).fetchone()
        if match is None:
            raise ValidationError("Match not found")
        if match["state"] in ("FINISHED", "VOIDED"):
            raise ValidationError("Cannot bet on finished/voided match")

        odds = self.get_odds(match_id)
        slip_number = self._new_slip_number()
        qr_payload = self._new_qr_payload()
        now = utc_now().isoformat()

        self._conn.execute(
            """
            INSERT INTO bet_slips(
              slip_number, match_id, side, amount, odds_snapshot_json, status,
              encoded_by, encoded_at, printed_at, payout_by, payout_at, payout_amount,
              qr_payload, device_id, archived_at
            )
            VALUES(?, ?, ?, ?, ?, 'ENCODED', ?, ?, NULL, NULL, NULL, NULL, ?, ?, NULL)
            """,
            (
                slip_number,
                match_id,
                side,
                amount,
                json.dumps(
                    {
                        "total_wala": odds.total_wala,
                        "total_meron": odds.total_meron,
                        "total_draw": odds.total_draw,
                        "total_all": odds.total_all,
                        "wala_multiplier": odds.wala_multiplier,
                        "meron_multiplier": odds.meron_multiplier,
                    },
                    ensure_ascii=False,
                ),
                encoded_by,
                now,
                qr_payload,
                device_id,
            ),
        )
        bet_id = int(self._conn.execute("SELECT id FROM bet_slips WHERE slip_number = ?", (slip_number,)).fetchone()["id"])
        if self._audit is not None:
            self._audit.log(
                actor=actor,
                action="BET_ENCODE",
                entity_type="bet_slip",
                entity_id=str(bet_id),
                new_state={"slip_number": slip_number, "match_id": match_id, "side": side, "amount": amount},
            )
        return {"id": bet_id, "slip_number": slip_number, "qr_payload": qr_payload, "odds": odds}

    def mark_printed(self, *, actor: Actor, bet_id: int) -> None:
        row = self._conn.execute(
            "SELECT id, status FROM bet_slips WHERE id = ?",
            (bet_id,),
        ).fetchone()
        if row is None:
            raise ValidationError("Bet slip not found")
        if row["status"] not in ("ENCODED", "PRINTED"):
            raise ValidationError("Slip cannot be printed in current state")
        now = utc_now().isoformat()
        self._conn.execute("UPDATE bet_slips SET status = 'PRINTED', printed_at = COALESCE(printed_at, ?) WHERE id = ?", (now, bet_id))
        if self._audit is not None:
            self._audit.log(actor=actor, action="BET_PRINT", entity_type="bet_slip", entity_id=str(bet_id), new_state={"printed_at": now})

    def compute_payout_for_slip(self, bet_id: int) -> int:
        slip = self._conn.execute(
            "SELECT id, match_id, side, amount FROM bet_slips WHERE id = ?",
            (bet_id,),
        ).fetchone()
        if slip is None:
            raise ValidationError("Bet slip not found")
        result = self._conn.execute("SELECT result_type FROM fight_results WHERE match_id = ?", (slip["match_id"],)).fetchone()
        if result is None:
            raise ValidationError("Match has no result yet")
        result_type = result["result_type"]
        amount = int(slip["amount"])

        # Cancelled / no contest: refund everyone (stake returned).
        if result_type in ("CANCELLED", "NO_CONTEST"):
            return amount

        # Draw: draw bettors are paid 5×; Wala/Meron are refunded.
        if result_type == "DRAW":
            if slip["side"] == "DRAW":
                return amount * 5
            return amount

        # Wala/Meron win: losing side gets 0; draw bets lose.
        if result_type in ("WALA", "MERON"):
            if slip["side"] != result_type:
                return 0
            odds = self.get_odds(int(slip["match_id"]))
            side_pool = odds.total_wala if result_type == "WALA" else odds.total_meron
            total_pool = odds.total_all
            if side_pool <= 0 or total_pool <= 0:
                return 0
            raw = amount * (total_pool / side_pool)
            return int(math.floor(raw))

        raise ValidationError("Unsupported result type")

    def payout_by_qr(
        self,
        *,
        actor: Actor,
        payout_by: int,
        qr_payload: str,
    ) -> dict[str, Any]:
        slip = self._conn.execute(
            """
            SELECT id, slip_number, match_id, status, payout_amount
            FROM bet_slips
            WHERE qr_payload = ?
            """,
            (qr_payload,),
        ).fetchone()
        if slip is None:
            raise ValidationError("Invalid QR / slip not found")
        if slip["status"] not in ("PRINTED",):
            raise ValidationError("Slip is not eligible for payout")
        payout_amount = self.compute_payout_for_slip(int(slip["id"]))
        now = utc_now().isoformat()
        self._conn.execute(
            """
            UPDATE bet_slips
            SET status = 'ARCHIVED',
                payout_by = ?,
                payout_at = ?,
                payout_amount = ?,
                archived_at = ?
            WHERE id = ?
            """,
            (payout_by, now, payout_amount, now, int(slip["id"])),
        )
        if self._audit is not None:
            self._audit.log(
                actor=actor,
                action="BET_PAYOUT",
                entity_type="bet_slip",
                entity_id=str(int(slip["id"])),
                previous_state={"status": slip["status"], "payout_amount": slip["payout_amount"]},
                new_state={"status": "ARCHIVED", "payout_amount": payout_amount},
            )
        return {"bet_id": int(slip["id"]), "slip_number": slip["slip_number"], "payout_amount": payout_amount}

    def archive_paid_slip(self, *, actor: Actor, bet_id: int) -> None:
        row = self._conn.execute("SELECT id, status, archived_at FROM bet_slips WHERE id = ?", (bet_id,)).fetchone()
        if row is None:
            return
        if row["status"] != "PAID":
            return
        now = utc_now().isoformat()
        self._conn.execute("UPDATE bet_slips SET status = 'ARCHIVED', archived_at = ? WHERE id = ?", (now, bet_id))
        if self._audit is not None:
            self._audit.log(actor=actor, action="BET_ARCHIVE", entity_type="bet_slip", entity_id=str(bet_id), new_state={"archived_at": now})
