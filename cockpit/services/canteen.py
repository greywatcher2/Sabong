from __future__ import annotations

import secrets
import sqlite3
from dataclasses import dataclass
from typing import Any

from cockpit.services.audit import Actor, AuditService
from cockpit.services.errors import ValidationError
from cockpit.utils.clock import utc_now


@dataclass(frozen=True)
class Item:
    id: int
    sku: str
    name: str
    unit_price: int
    is_active: bool


class CanteenService:
    """
    Canteen sales and inventory.

    Accounting rules:
    - Cash-only.
    - Canteen cash drawer is separate from betting.
    """

    def __init__(self, conn: sqlite3.Connection, audit: AuditService | None) -> None:
        self._conn = conn
        self._audit = audit

    def list_items(self) -> list[Item]:
        rows = self._conn.execute(
            "SELECT id, sku, name, unit_price, is_active FROM canteen_items WHERE is_active = 1 ORDER BY name",
        ).fetchall()
        return [
            Item(
                id=int(r["id"]),
                sku=r["sku"],
                name=r["name"],
                unit_price=int(r["unit_price"]),
                is_active=bool(r["is_active"]),
            )
            for r in rows
        ]

    def upsert_item(self, *, actor: Actor, sku: str, name: str, unit_price: int, created_by: int) -> int:
        if unit_price < 0:
            raise ValidationError("Unit price must be >= 0")
        now = utc_now().isoformat()
        existing = self._conn.execute("SELECT id, name, unit_price FROM canteen_items WHERE sku = ?", (sku,)).fetchone()
        if existing is None:
            cur = self._conn.execute(
                """
                INSERT INTO canteen_items(sku, name, unit_price, is_active, created_at)
                VALUES(?, ?, ?, 1, ?)
                """,
                (sku, name, unit_price, now),
            )
            item_id = int(cur.lastrowid)
            if self._audit is not None:
                self._audit.log(actor=actor, action="CANTEEN_ITEM_CREATE", entity_type="canteen_item", entity_id=str(item_id), new_state={"sku": sku, "name": name, "unit_price": unit_price})
            return item_id

        self._conn.execute("UPDATE canteen_items SET name = ?, unit_price = ? WHERE sku = ?", (name, unit_price, sku))
        if self._audit is not None:
            self._audit.log(
                actor=actor,
                action="CANTEEN_ITEM_UPDATE",
                entity_type="canteen_item",
                entity_id=str(int(existing["id"])),
                previous_state={"name": existing["name"], "unit_price": int(existing["unit_price"])},
                new_state={"name": name, "unit_price": unit_price},
            )
        return int(existing["id"])

    def stock_in(self, *, actor: Actor, created_by: int, item_id: int, qty: int, unit_cost: int | None, notes: str | None) -> None:
        if qty <= 0:
            raise ValidationError("Qty must be > 0")
        if unit_cost is not None and unit_cost < 0:
            raise ValidationError("Unit cost must be >= 0")
        self._conn.execute(
            """
            INSERT INTO canteen_stock_movements(item_id, movement_type, qty, unit_cost, reference_type, reference_id, created_by, created_at)
            VALUES (?, 'IN', ?, ?, 'MANUAL', NULL, ?, ?)
            """,
            (item_id, qty, unit_cost, created_by, utc_now().isoformat()),
        )
        if self._audit is not None:
            self._audit.log(actor=actor, action="CANTEEN_STOCK_IN", entity_type="canteen_item", entity_id=str(item_id), new_state={"qty": qty, "unit_cost": unit_cost, "notes": notes})

    def current_stock(self, item_id: int) -> int:
        row = self._conn.execute(
            """
            SELECT
              COALESCE(SUM(CASE WHEN movement_type = 'IN' THEN qty WHEN movement_type = 'OUT' THEN -qty ELSE 0 END), 0) AS stock
            FROM canteen_stock_movements
            WHERE item_id = ?
            """,
            (item_id,),
        ).fetchone()
        return int(row["stock"])

    def _new_receipt_number(self) -> str:
        token = secrets.token_hex(4).upper()
        return f"C{utc_now().strftime('%Y%m%d')}-{token}"

    def create_sale(self, *, actor: Actor, drawer_id: int, sold_by: int, lines: list[dict[str, Any]]) -> dict[str, Any]:
        if not lines:
            raise ValidationError("Sale requires at least one item")
        receipt = self._new_receipt_number()
        sold_at = utc_now().isoformat()
        total = 0
        normalized: list[dict[str, int]] = []
        for line in lines:
            item_id = int(line["item_id"])
            qty = int(line["qty"])
            if qty <= 0:
                raise ValidationError("Qty must be > 0")
            item = self._conn.execute("SELECT id, unit_price FROM canteen_items WHERE id = ? AND is_active = 1", (item_id,)).fetchone()
            if item is None:
                raise ValidationError("Invalid item")
            unit_price = int(item["unit_price"])
            line_total = unit_price * qty
            total += line_total
            normalized.append({"item_id": item_id, "qty": qty, "unit_price": unit_price, "line_total": line_total})

            stock = self.current_stock(item_id)
            if stock < qty:
                raise ValidationError("Insufficient stock")

        cur = self._conn.execute(
            """
            INSERT INTO canteen_sales(receipt_number, drawer_id, sold_by, sold_at, total_amount, status)
            VALUES (?, ?, ?, ?, ?, 'PAID')
            """,
            (receipt, drawer_id, sold_by, sold_at, total),
        )
        sale_id = int(cur.lastrowid)
        for line in normalized:
            self._conn.execute(
                """
                INSERT INTO canteen_sale_lines(sale_id, item_id, qty, unit_price, line_total)
                VALUES (?, ?, ?, ?, ?)
                """,
                (sale_id, line["item_id"], line["qty"], line["unit_price"], line["line_total"]),
            )
            self._conn.execute(
                """
                INSERT INTO canteen_stock_movements(item_id, movement_type, qty, unit_cost, reference_type, reference_id, created_by, created_at)
                VALUES (?, 'OUT', ?, NULL, 'SALE', ?, ?, ?)
                """,
                (line["item_id"], line["qty"], str(sale_id), sold_by, sold_at),
            )

        if self._audit is not None:
            self._audit.log(
                actor=actor,
                action="CANTEEN_SALE",
                entity_type="canteen_sale",
                entity_id=str(sale_id),
                new_state={"receipt_number": receipt, "total_amount": total, "lines": normalized},
            )
        return {"sale_id": sale_id, "receipt_number": receipt, "total_amount": total}
