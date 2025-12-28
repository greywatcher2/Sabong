from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Literal

from cockpit.services.audit import Actor, AuditService
from cockpit.services.errors import ValidationError
from cockpit.utils.clock import utc_now


DrawerType = Literal["BETTING_CASHIER", "CANTEEN"]


@dataclass(frozen=True)
class CashDrawer:
    id: int
    drawer_type: DrawerType
    name: str
    owner_user_id: int | None
    current_cash: int


class CashService:
    """
    Separate cash tracking per module.

    Non-negotiable rule:
    - Betting cash and canteen cash must never be merged.
    """

    def __init__(self, conn: sqlite3.Connection, audit: AuditService) -> None:
        self._conn = conn
        self._audit = audit

    def open_drawer(
        self,
        *,
        actor: Actor,
        drawer_type: DrawerType,
        name: str,
        owner_user_id: int | None,
        opening_cash: int,
    ) -> int:
        if opening_cash < 0:
            raise ValidationError("Opening cash must be >= 0")
        now = utc_now().isoformat()
        cur = self._conn.execute(
            """
            INSERT INTO cash_drawers(drawer_type, name, owner_user_id, opened_at, closed_at, opening_cash, current_cash)
            VALUES (?, ?, ?, ?, NULL, ?, ?)
            """,
            (drawer_type, name, owner_user_id, now, opening_cash, opening_cash),
        )
        drawer_id = int(cur.lastrowid)
        self._audit.log(
            actor=actor,
            action="DRAWER_OPEN",
            entity_type="cash_drawer",
            entity_id=str(drawer_id),
            new_state={"drawer_type": drawer_type, "name": name, "owner_user_id": owner_user_id, "opening_cash": opening_cash},
        )
        return drawer_id

    def get_or_open_user_drawer(self, *, actor: Actor, drawer_type: DrawerType, user_id: int) -> int:
        row = self._conn.execute(
            "SELECT id FROM cash_drawers WHERE drawer_type = ? AND owner_user_id = ? AND closed_at IS NULL",
            (drawer_type, user_id),
        ).fetchone()
        if row is not None:
            return int(row["id"])
        return self.open_drawer(actor=actor, drawer_type=drawer_type, name=f"{drawer_type}#{user_id}", owner_user_id=user_id, opening_cash=0)

    def record_movement(
        self,
        *,
        actor: Actor,
        created_by: int,
        drawer_id: int,
        movement_type: str,
        amount: int,
        reference_type: str | None,
        reference_id: str | None,
        notes: str | None,
    ) -> None:
        if amount <= 0:
            raise ValidationError("Amount must be > 0")
        now = utc_now().isoformat()
        self._conn.execute(
            """
            INSERT INTO cash_movements(drawer_id, movement_type, reference_type, reference_id, amount, notes, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (drawer_id, movement_type, reference_type, reference_id, amount, notes, created_by, now),
        )
        # We only update the specific drawer; betting and canteen drawers stay separate by design.
        delta = amount if movement_type in ("BET_IN", "ADJUSTMENT_IN", "CANTEEN_SALE_IN") else -amount
        self._conn.execute("UPDATE cash_drawers SET current_cash = current_cash + ? WHERE id = ?", (delta, drawer_id))
        self._audit.log(
            actor=actor,
            action="CASH_MOVE",
            entity_type="cash_movement",
            entity_id=None,
            new_state={
                "drawer_id": drawer_id,
                "movement_type": movement_type,
                "amount": amount,
                "delta": delta,
                "reference_type": reference_type,
                "reference_id": reference_id,
            },
        )

