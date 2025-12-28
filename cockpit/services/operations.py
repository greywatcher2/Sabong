from __future__ import annotations

import sqlite3

from cockpit.db.connection import transaction
from cockpit.services.audit import Actor, AuditService
from cockpit.services.betting import BettingService
from cockpit.services.cash import CashService
from cockpit.services.canteen import CanteenService
from cockpit.services.errors import ValidationError


class OperationsService:
    """
    Orchestrates multi-table domain operations in a single transaction.

    This keeps integrity for:
    - Bet encode + cashier cash-in
    - Bet payout/refund + cashier cash-out
    - Canteen sale + canteen cash-in + stock-out
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self.audit = AuditService(conn)
        self.betting = BettingService(conn, self.audit)
        self.cash = CashService(conn, self.audit)
        self.canteen = CanteenService(conn, self.audit)

    def encode_bet_with_cash(
        self,
        *,
        actor: Actor,
        cashier_user_id: int,
        device_id: str,
        match_id: int,
        side: str,
        amount: int,
    ) -> dict:
        with transaction(self._conn):
            drawer_id = self.cash.get_or_open_user_drawer(actor=actor, drawer_type="BETTING_CASHIER", user_id=cashier_user_id)
            slip = self.betting.encode_bet(
                actor=actor,
                encoded_by=cashier_user_id,
                device_id=device_id,
                match_id=match_id,
                side=side,
                amount=amount,
            )
            self.cash.record_movement(
                actor=actor,
                created_by=cashier_user_id,
                drawer_id=drawer_id,
                movement_type="BET_IN",
                amount=amount,
                reference_type="BET_SLIP",
                reference_id=str(slip["id"]),
                notes=None,
            )
            return slip

    def payout_bet_with_cash(
        self,
        *,
        actor: Actor,
        cashier_user_id: int,
        qr_payload: str,
    ) -> dict:
        with transaction(self._conn):
            drawer_id = self.cash.get_or_open_user_drawer(actor=actor, drawer_type="BETTING_CASHIER", user_id=cashier_user_id)
            result = self.betting.payout_by_qr(actor=actor, payout_by=cashier_user_id, qr_payload=qr_payload)
            payout_amount = int(result["payout_amount"])
            if payout_amount < 0:
                raise ValidationError("Invalid payout amount")
            if payout_amount > 0:
                self.cash.record_movement(
                    actor=actor,
                    created_by=cashier_user_id,
                    drawer_id=drawer_id,
                    movement_type="PAYOUT_OUT",
                    amount=payout_amount,
                    reference_type="BET_SLIP",
                    reference_id=str(result["bet_id"]),
                    notes=None,
                )
            return result

    def canteen_sale_with_cash(
        self,
        *,
        actor: Actor,
        canteen_user_id: int,
        drawer_id: int | None,
        lines: list[dict],
    ) -> dict:
        with transaction(self._conn):
            if drawer_id is None:
                drawer_id = self.cash.get_or_open_user_drawer(actor=actor, drawer_type="CANTEEN", user_id=canteen_user_id)
            sale = self.canteen.create_sale(actor=actor, drawer_id=drawer_id, sold_by=canteen_user_id, lines=lines)
            self.cash.record_movement(
                actor=actor,
                created_by=canteen_user_id,
                drawer_id=drawer_id,
                movement_type="CANTEEN_SALE_IN",
                amount=int(sale["total_amount"]),
                reference_type="CANTEEN_SALE",
                reference_id=str(sale["sale_id"]),
                notes=None,
            )
            return sale

