from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class Permission:
    code: str
    description: str


DEFAULT_PERMISSIONS: tuple[Permission, ...] = (
    Permission("ADMIN_ALL", "Full system control"),
    Permission("USER_MANAGE", "Manage users"),
    Permission("ROLE_MANAGE", "Manage roles and permissions"),
    Permission("FIGHT_REGISTER", "Register matches and entries"),
    Permission("FIGHT_CANCEL_PRELOCK", "Cancel match or entry before lock"),
    Permission("FIGHT_CONTROL", "Start/stop matches"),
    Permission("FIGHT_RESULT_SET", "Set match results"),
    Permission("FIGHT_OVERRIDE", "Override fight state/result (audited)"),
    Permission("BET_ENCODE", "Encode bets and print slips"),
    Permission("BET_PAYOUT", "Payout / refund via QR"),
    Permission("VIEW_DASHBOARD", "View monitoring dashboard"),
    Permission("VIEW_REPORTS", "View reports"),
    Permission("VIEW_AUDIT_LOG", "View immutable logs"),
    Permission("CANTEEN_POS", "Use canteen POS"),
    Permission("CANTEEN_VIEW_PUBLIC", "Show canteen public display"),
    Permission("PUBLIC_DISPLAY", "Show public fight display mode"),
)


DEFAULT_ROLES: dict[str, list[str]] = {
    "Admin": ["ADMIN_ALL"],
    "Cashier": ["BET_ENCODE", "BET_PAYOUT", "VIEW_DASHBOARD"],
    "Fight Registrar": ["FIGHT_REGISTER", "FIGHT_CANCEL_PRELOCK", "VIEW_DASHBOARD"],
    "Canteen": ["CANTEEN_POS", "CANTEEN_VIEW_PUBLIC", "VIEW_DASHBOARD"],
    "Supervisor / Auditor": ["VIEW_DASHBOARD", "VIEW_REPORTS", "VIEW_AUDIT_LOG"],
}


class RBACService:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def seed_defaults(self) -> None:
        for perm in DEFAULT_PERMISSIONS:
            self._conn.execute(
                "INSERT OR IGNORE INTO permissions(code, description) VALUES (?, ?)",
                (perm.code, perm.description),
            )

        for role_name, perm_codes in DEFAULT_ROLES.items():
            self._conn.execute(
                "INSERT OR IGNORE INTO roles(name, description) VALUES (?, ?)",
                (role_name, None),
            )
            role_id = self._conn.execute("SELECT id FROM roles WHERE name = ?", (role_name,)).fetchone()[
                "id"
            ]
            for code in perm_codes:
                perm_id = self._conn.execute("SELECT id FROM permissions WHERE code = ?", (code,)).fetchone()[
                    "id"
                ]
                self._conn.execute(
                    "INSERT OR IGNORE INTO role_permissions(role_id, permission_id) VALUES (?, ?)",
                    (role_id, perm_id),
                )

    def user_permissions(self, user_id: int) -> set[str]:
        rows = self._conn.execute(
            """
            SELECT p.code
            FROM permissions p
            JOIN role_permissions rp ON rp.permission_id = p.id
            JOIN user_roles ur ON ur.role_id = rp.role_id
            WHERE ur.user_id = ?
            """,
            (user_id,),
        ).fetchall()
        codes = {r["code"] for r in rows}
        if "ADMIN_ALL" in codes:
            return {"ADMIN_ALL"} | {p.code for p in DEFAULT_PERMISSIONS}
        return codes

    def has(self, user_id: int, perm_code: str) -> bool:
        return perm_code in self.user_permissions(user_id)

