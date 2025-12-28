from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import timedelta

from cockpit.services.audit import Actor, AuditService
from cockpit.services.errors import AuthError
from cockpit.utils.clock import utc_now
from cockpit.utils.security import hash_password, verify_password


_SESSION_STALE_AFTER_SECONDS = 30


@dataclass(frozen=True)
class User:
    id: int
    username: str
    full_name: str | None
    is_active: bool
    is_frozen: bool


class AuthService:
    def __init__(self, conn: sqlite3.Connection, audit: AuditService) -> None:
        self._conn = conn
        self._audit = audit

    def ensure_bootstrap_admin(self) -> bool:
        """
        Returns True if a bootstrap is required (no users exist).
        """
        row = self._conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()
        return int(row["c"]) == 0

    def create_user(
        self,
        *,
        actor: Actor,
        username: str,
        password: str,
        full_name: str | None,
        role_names: list[str],
    ) -> int:
        now = utc_now().isoformat()
        pw_hash = hash_password(password)
        cur = self._conn.execute(
            """
            INSERT INTO users(username, password_hash, full_name, is_active, is_frozen, created_at, updated_at)
            VALUES (?, ?, ?, 1, 0, ?, ?)
            """,
            (username, pw_hash, full_name, now, now),
        )
        user_id = int(cur.lastrowid)
        for role_name in role_names:
            role = self._conn.execute("SELECT id FROM roles WHERE name = ?", (role_name,)).fetchone()
            if role is None:
                raise AuthError(f"Role not found: {role_name}")
            self._conn.execute("INSERT OR IGNORE INTO user_roles(user_id, role_id) VALUES (?, ?)", (user_id, role["id"]))

        self._audit.log(
            actor=actor,
            action="USER_CREATE",
            entity_type="user",
            entity_id=str(user_id),
            previous_state=None,
            new_state={"id": user_id, "username": username, "full_name": full_name, "roles": role_names},
        )
        return user_id

    def set_user_frozen(self, *, actor: Actor, user_id: int, frozen: bool, reason: str) -> None:
        prev = self._conn.execute(
            "SELECT id, username, is_frozen FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if prev is None:
            raise AuthError("User not found")
        self._conn.execute("UPDATE users SET is_frozen = ?, updated_at = ? WHERE id = ?", (1 if frozen else 0, utc_now().isoformat(), user_id))
        self._audit.log(
            actor=actor,
            action="USER_FREEZE" if frozen else "USER_UNFREEZE",
            entity_type="user",
            entity_id=str(user_id),
            previous_state={"id": user_id, "username": prev["username"], "is_frozen": bool(prev["is_frozen"])},
            new_state={"id": user_id, "username": prev["username"], "is_frozen": frozen},
            metadata={"reason": reason},
        )

    def cleanup_stale_sessions(self, *, actor: Actor) -> int:
        now = utc_now()
        stale_before = (now - timedelta(seconds=_SESSION_STALE_AFTER_SECONDS)).isoformat()
        rows = self._conn.execute(
            """
            SELECT id, user_id, device_id, last_seen_at
            FROM sessions
            WHERE logged_out_at IS NULL
              AND COALESCE(last_seen_at, logged_in_at) <= ?
            """,
            (stale_before,),
        ).fetchall()
        if not rows:
            return 0

        logged_out_at = now.isoformat()
        self._conn.execute(
            """
            UPDATE sessions
            SET logged_out_at = ?
            WHERE logged_out_at IS NULL
              AND COALESCE(last_seen_at, logged_in_at) <= ?
            """,
            (logged_out_at, stale_before),
        )
        for r in rows:
            self._audit.log(
                actor=actor,
                action="SESSION_AUTO_LOGOUT",
                entity_type="session",
                entity_id=str(int(r["id"])),
                previous_state={"session_id": int(r["id"]), "user_id": int(r["user_id"]), "device_id": r["device_id"]},
                new_state={"session_id": int(r["id"]), "logged_out_at": logged_out_at},
                metadata={"reason": "STALE"},
            )
        return len(rows)

    def heartbeat(self, *, session_id: int) -> None:
        now = utc_now().isoformat()
        self._conn.execute(
            "UPDATE sessions SET last_seen_at = ? WHERE id = ? AND logged_out_at IS NULL",
            (now, session_id),
        )

    def login(self, *, username: str, password: str, device_id: str) -> tuple[User, int]:
        row = self._conn.execute(
            "SELECT id, username, full_name, password_hash, is_active, is_frozen FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if row is None:
            raise AuthError("Invalid username/password")
        if not bool(row["is_active"]) or bool(row["is_frozen"]):
            raise AuthError("User is inactive or frozen")
        if not verify_password(password, row["password_hash"]):
            raise AuthError("Invalid username/password")

        self.cleanup_stale_sessions(actor=Actor(user_id=None, device_id=device_id))

        active = self._conn.execute(
            "SELECT id FROM sessions WHERE user_id = ? AND logged_out_at IS NULL",
            (row["id"],),
        ).fetchone()
        if active is not None:
            raise AuthError("User already logged in on another device")

        now = utc_now().isoformat()
        cur = self._conn.execute(
            "INSERT INTO sessions(user_id, device_id, logged_in_at, last_seen_at, logged_out_at) VALUES (?, ?, ?, ?, NULL)",
            (row["id"], device_id, now, now),
        )
        session_id = int(cur.lastrowid)
        user = User(
            id=int(row["id"]),
            username=row["username"],
            full_name=row["full_name"],
            is_active=bool(row["is_active"]),
            is_frozen=bool(row["is_frozen"]),
        )
        self._audit.log(
            actor=Actor(user_id=user.id, device_id=device_id),
            action="LOGIN",
            entity_type="session",
            entity_id=str(session_id),
            new_state={"session_id": session_id, "user_id": user.id, "username": user.username},
        )
        return user, session_id

    def logout(self, *, actor: Actor, session_id: int) -> None:
        row = self._conn.execute("SELECT id, user_id, device_id, logged_out_at FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            return
        if row["logged_out_at"] is not None:
            return
        logged_out_at = utc_now().isoformat()
        self._conn.execute("UPDATE sessions SET logged_out_at = ? WHERE id = ?", (logged_out_at, session_id))
        self._audit.log(
            actor=actor,
            action="LOGOUT",
            entity_type="session",
            entity_id=str(session_id),
            previous_state={"session_id": session_id, "user_id": int(row["user_id"]), "device_id": row["device_id"]},
            new_state={"session_id": session_id, "logged_out_at": logged_out_at},
        )
