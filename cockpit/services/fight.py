from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from cockpit.services.audit import Actor, AuditService
from cockpit.services.errors import ValidationError
from cockpit.utils.clock import utc_now


@dataclass(frozen=True)
class FightMatch:
    id: int
    match_number: str
    structure_code: str
    rounds: int
    state: str
    locked_at: str | None
    started_at: str | None
    stopped_at: str | None


class FightService:
    """
    Official match and entry registration.

    Domain rules enforced:
    - A fight becomes LOCKED once betting starts (first bet insert trigger sets locked_at/state).
    - No editing entries after lock (SQLite trigger).
    - Manual start/stop timestamps are recorded.
    """

    def __init__(self, conn: sqlite3.Connection, audit: AuditService) -> None:
        self._conn = conn
        self._audit = audit

    def create_match(
        self,
        *,
        actor: Actor,
        match_number: str,
        structure_code: str,
        rounds: int,
        created_by: int,
    ) -> int:
        if rounds <= 0:
            raise ValidationError("Rounds must be >= 1")
        structure = self._conn.execute(
            "SELECT code FROM fight_structures WHERE code = ? AND is_active = 1",
            (structure_code,),
        ).fetchone()
        if structure is None:
            raise ValidationError("Invalid or inactive fight structure")
        now = utc_now().isoformat()
        cur = self._conn.execute(
            """
            INSERT INTO fight_matches(match_number, fight_number, structure_code, rounds, state, locked_at, started_at, stopped_at, created_by, created_at)
            VALUES (?, NULL, ?, ?, 'DRAFT', NULL, NULL, NULL, ?, ?)
            """,
            (match_number, structure_code, rounds, created_by, now),
        )
        match_id = int(cur.lastrowid)
        self._conn.execute("UPDATE fight_matches SET fight_number = COALESCE(fight_number, ?) WHERE id = ?", (match_id, match_id))
        self._audit.log(
            actor=actor,
            action="MATCH_CREATE",
            entity_type="fight_match",
            entity_id=str(match_id),
            new_state={"match_number": match_number, "fight_number": match_id, "structure_code": structure_code, "rounds": rounds, "state": "DRAFT"},
        )
        return match_id

    def add_entry(
        self,
        *,
        actor: Actor,
        match_id: int,
        side: str,
        entry_name: str,
        owner: str,
        num_cocks: int,
        weight_per_cock: float,
        color: str,
    ) -> int:
        if side not in ("WALA", "MERON"):
            raise ValidationError("Side must be WALA or MERON")
        if num_cocks <= 0:
            raise ValidationError("Number of cocks must be >= 1")
        if weight_per_cock <= 0:
            raise ValidationError("Weight must be > 0")

        now = utc_now().isoformat()
        cur = self._conn.execute(
            """
            INSERT INTO fight_entries(match_id, side, entry_name, owner, num_cocks, weight_per_cock, color, created_at, updated_at, deleted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (match_id, side, entry_name, owner, num_cocks, weight_per_cock, color, now, now),
        )
        entry_id = int(cur.lastrowid)
        self._audit.log(
            actor=actor,
            action="ENTRY_CREATE",
            entity_type="fight_entry",
            entity_id=str(entry_id),
            new_state={
                "match_id": match_id,
                "side": side,
                "entry_name": entry_name,
                "owner": owner,
                "num_cocks": num_cocks,
                "weight_per_cock": weight_per_cock,
                "color": color,
            },
        )
        return entry_id

    def cancel_entry_prelock(self, *, actor: Actor, entry_id: int, reason: str) -> None:
        row = self._conn.execute(
            """
            SELECT fe.id, fe.match_id, fe.side, fe.entry_name, fe.owner, fe.deleted_at, fm.locked_at
            FROM fight_entries fe
            JOIN fight_matches fm ON fm.id = fe.match_id
            WHERE fe.id = ?
            """,
            (entry_id,),
        ).fetchone()
        if row is None:
            raise ValidationError("Entry not found")
        if row["locked_at"] is not None:
            raise ValidationError("Fight is locked; cannot cancel entry")
        if row["deleted_at"] is not None:
            return
        now = utc_now().isoformat()
        self._conn.execute("UPDATE fight_entries SET deleted_at = ?, updated_at = ? WHERE id = ?", (now, now, entry_id))
        self._audit.log(
            actor=actor,
            action="ENTRY_CANCEL_PRELOCK",
            entity_type="fight_entry",
            entity_id=str(entry_id),
            previous_state={"deleted_at": None},
            new_state={"deleted_at": now},
            metadata={"reason": reason},
        )

    def start_match(self, *, actor: Actor, match_id: int) -> None:
        prev = self._conn.execute("SELECT id, state, started_at FROM fight_matches WHERE id = ?", (match_id,)).fetchone()
        if prev is None:
            raise ValidationError("Match not found")
        if prev["state"] not in ("LOCKED", "DRAFT"):
            raise ValidationError("Match cannot be started from current state")
        now = utc_now().isoformat()
        self._conn.execute(
            "UPDATE fight_matches SET state = 'ACTIVE', started_at = COALESCE(started_at, ?) WHERE id = ?",
            (now, match_id),
        )
        self._audit.log(
            actor=actor,
            action="MATCH_START",
            entity_type="fight_match",
            entity_id=str(match_id),
            previous_state={"state": prev["state"], "started_at": prev["started_at"]},
            new_state={"state": "ACTIVE", "started_at": now},
        )

    def stop_match(self, *, actor: Actor, match_id: int) -> None:
        prev = self._conn.execute("SELECT id, state, stopped_at FROM fight_matches WHERE id = ?", (match_id,)).fetchone()
        if prev is None:
            raise ValidationError("Match not found")
        if prev["state"] != "ACTIVE":
            raise ValidationError("Match must be ACTIVE to stop")
        now = utc_now().isoformat()
        self._conn.execute("UPDATE fight_matches SET stopped_at = ? WHERE id = ?", (now, match_id))
        self._audit.log(
            actor=actor,
            action="MATCH_STOP",
            entity_type="fight_match",
            entity_id=str(match_id),
            previous_state={"stopped_at": prev["stopped_at"]},
            new_state={"stopped_at": now},
        )

    def set_result(
        self,
        *,
        actor: Actor,
        match_id: int,
        result_type: str,
        decided_by: int,
        notes: str | None = None,
        override: bool = False,
    ) -> None:
        if result_type not in ("WALA", "MERON", "DRAW", "CANCELLED", "NO_CONTEST"):
            raise ValidationError("Invalid result type")
        prev_match = self._conn.execute("SELECT id, state FROM fight_matches WHERE id = ?", (match_id,)).fetchone()
        if prev_match is None:
            raise ValidationError("Match not found")
        if prev_match["state"] == "VOIDED" and not override:
            raise ValidationError("Match is voided")

        prev_result = self._conn.execute("SELECT match_id, result_type FROM fight_results WHERE match_id = ?", (match_id,)).fetchone()
        now = utc_now().isoformat()
        self._conn.execute(
            """
            INSERT INTO fight_results(match_id, result_type, decided_by, decided_at, notes)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(match_id) DO UPDATE SET
              result_type = excluded.result_type,
              decided_by = excluded.decided_by,
              decided_at = excluded.decided_at,
              notes = excluded.notes
            """,
            (match_id, result_type, decided_by, now, notes),
        )
        self._conn.execute("UPDATE fight_matches SET state = 'FINISHED' WHERE id = ? AND state != 'VOIDED'", (match_id,))
        self._audit.log(
            actor=actor,
            action="MATCH_RESULT_OVERRIDE" if (prev_result is not None and override) else "MATCH_RESULT_SET",
            entity_type="fight_result",
            entity_id=str(match_id),
            previous_state={"result_type": prev_result["result_type"]} if prev_result is not None else None,
            new_state={"result_type": result_type, "decided_by": decided_by, "decided_at": now, "notes": notes},
        )

    def void_match(self, *, actor: Actor, match_id: int, reason: str) -> None:
        prev = self._conn.execute("SELECT id, state FROM fight_matches WHERE id = ?", (match_id,)).fetchone()
        if prev is None:
            raise ValidationError("Match not found")
        self._conn.execute("UPDATE fight_matches SET state = 'VOIDED' WHERE id = ?", (match_id,))
        if actor.user_id is not None:
            now = utc_now().isoformat()
            self._conn.execute(
                """
                INSERT INTO fight_results(match_id, result_type, decided_by, decided_at, notes)
                VALUES (?, 'CANCELLED', ?, ?, ?)
                ON CONFLICT(match_id) DO UPDATE SET
                  result_type = excluded.result_type,
                  decided_by = excluded.decided_by,
                  decided_at = excluded.decided_at,
                  notes = excluded.notes
                """,
                (match_id, actor.user_id, now, f"VOIDED: {reason}"),
            )
        self._audit.log(
            actor=actor,
            action="MATCH_VOID",
            entity_type="fight_match",
            entity_id=str(match_id),
            previous_state={"state": prev["state"]},
            new_state={"state": "VOIDED"},
            metadata={"reason": reason},
        )

    def cancel_match_prelock(self, *, actor: Actor, match_id: int, reason: str) -> None:
        prev = self._conn.execute("SELECT id, state, locked_at FROM fight_matches WHERE id = ?", (match_id,)).fetchone()
        if prev is None:
            raise ValidationError("Match not found")
        if prev["locked_at"] is not None:
            raise ValidationError("Fight is locked; cannot cancel pre-lock")
        if prev["state"] == "VOIDED":
            return
        self._conn.execute("UPDATE fight_matches SET state = 'VOIDED' WHERE id = ?", (match_id,))
        self._audit.log(
            actor=actor,
            action="MATCH_CANCEL_PRELOCK",
            entity_type="fight_match",
            entity_id=str(match_id),
            previous_state={"state": prev["state"]},
            new_state={"state": "VOIDED"},
            metadata={"reason": reason},
        )

    def get_match_snapshot(self, match_id: int) -> dict[str, Any]:
        m = self._conn.execute(
            "SELECT id, match_number, structure_code, rounds, state, locked_at, started_at, stopped_at FROM fight_matches WHERE id = ?",
            (match_id,),
        ).fetchone()
        if m is None:
            raise ValidationError("Match not found")
        entries = self._conn.execute(
            """
            SELECT id, side, entry_name, owner, num_cocks, weight_per_cock, color
            FROM fight_entries
            WHERE match_id = ? AND deleted_at IS NULL
            ORDER BY side, id
            """,
            (match_id,),
        ).fetchall()
        return {
            "match": dict(m),
            "entries": [dict(e) for e in entries],
        }

