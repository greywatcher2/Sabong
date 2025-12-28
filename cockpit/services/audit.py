from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Mapping

from cockpit.utils.clock import utc_now


@dataclass(frozen=True)
class Actor:
    user_id: int | None
    device_id: str


class AuditService:
    """
    Immutable audit logging (append-only).

    Every privileged action should write exactly one row describing:
    - who performed it (actor_user_id, actor_device_id)
    - what happened (action, entity_type/entity_id)
    - state transition (previous_state_json/new_state_json)
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def log(
        self,
        *,
        actor: Actor,
        action: str,
        entity_type: str,
        entity_id: str | None,
        previous_state: Mapping[str, Any] | None = None,
        new_state: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO audit_log (
              actor_user_id,
              actor_device_id,
              action,
              entity_type,
              entity_id,
              previous_state_json,
              new_state_json,
              metadata_json,
              created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                actor.user_id,
                actor.device_id,
                action,
                entity_type,
                entity_id,
                json.dumps(previous_state, ensure_ascii=False) if previous_state is not None else None,
                json.dumps(new_state, ensure_ascii=False) if new_state is not None else None,
                json.dumps(metadata, ensure_ascii=False) if metadata is not None else None,
                utc_now().isoformat(),
            ),
        )

