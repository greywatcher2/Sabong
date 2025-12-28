import sqlite3
import unittest

from cockpit.db.migrate import initialize_database
from cockpit.services.audit import Actor, AuditService
from cockpit.services.auth import AuthService
from cockpit.services.betting import BettingService
from cockpit.services.fight import FightService
from cockpit.services.rbac import RBACService
from cockpit.utils.security import hash_password


class DomainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        initialize_database(self.conn)
        RBACService(self.conn).seed_defaults()
        self.audit = AuditService(self.conn)
        self.actor = Actor(user_id=None, device_id="TEST")

        now = "2025-01-01T00:00:00+00:00"
        self.conn.execute(
            "INSERT INTO users(username, password_hash, full_name, is_active, is_frozen, created_at, updated_at) VALUES(?, ?, ?, 1, 0, ?, ?)",
            ("admin", hash_password("pw"), "Admin", now, now),
        )
        self.user_id = int(self.conn.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()["id"])
        self.user_actor = Actor(user_id=self.user_id, device_id="TEST")

    def tearDown(self) -> None:
        self.conn.close()

    def test_audit_log_is_append_only(self) -> None:
        self.audit.log(actor=self.user_actor, action="X", entity_type="t", entity_id="1", new_state={"a": 1})
        log_id = int(self.conn.execute("SELECT id FROM audit_log").fetchone()["id"])
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("UPDATE audit_log SET action = 'Y' WHERE id = ?", (log_id,))
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("DELETE FROM audit_log WHERE id = ?", (log_id,))

    def test_single_active_session_per_user(self) -> None:
        auth = AuthService(self.conn, self.audit)
        user, _session = auth.login(username="admin", password="pw", device_id="A")
        self.assertEqual(user.id, self.user_id)
        with self.assertRaises(Exception):
            auth.login(username="admin", password="pw", device_id="B")

    def test_stale_session_auto_logout_allows_new_login(self) -> None:
        auth = AuthService(self.conn, self.audit)
        _user, session_id = auth.login(username="admin", password="pw", device_id="A")
        self.conn.execute(
            "UPDATE sessions SET last_seen_at = ?, logged_out_at = NULL WHERE id = ?",
            ("2000-01-01T00:00:00+00:00", session_id),
        )
        user2, session2 = auth.login(username="admin", password="pw", device_id="B")
        self.assertEqual(user2.id, self.user_id)
        self.assertNotEqual(session2, session_id)
        old = self.conn.execute("SELECT logged_out_at FROM sessions WHERE id = ?", (session_id,)).fetchone()
        self.assertIsNotNone(old["logged_out_at"])

    def test_match_locks_on_first_bet_and_blocks_entry_edit(self) -> None:
        fight = FightService(self.conn, self.audit)
        betting = BettingService(self.conn, self.audit)

        match_id = fight.create_match(actor=self.user_actor, match_number="M1", structure_code="SINGLE", rounds=1, created_by=self.user_id)
        entry_id = fight.add_entry(
            actor=self.user_actor,
            match_id=match_id,
            side="WALA",
            entry_name="WALA A",
            owner="O",
            num_cocks=1,
            weight_per_cock=2.0,
            color="RED",
        )
        slip = betting.encode_bet(actor=self.user_actor, encoded_by=self.user_id, device_id="TEST", match_id=match_id, side="WALA", amount=10)
        self.assertIsNotNone(slip["qr_payload"])
        locked = self.conn.execute("SELECT locked_at, state FROM fight_matches WHERE id = ?", (match_id,)).fetchone()
        self.assertIsNotNone(locked["locked_at"])
        self.assertIn(locked["state"], ("LOCKED", "DRAFT", "ACTIVE", "FINISHED", "VOIDED"))

        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("UPDATE fight_entries SET entry_name = 'X' WHERE id = ?", (entry_id,))

    def test_payout_rules(self) -> None:
        fight = FightService(self.conn, self.audit)
        betting = BettingService(self.conn, self.audit)

        match_id = fight.create_match(actor=self.user_actor, match_number="M2", structure_code="SINGLE", rounds=1, created_by=self.user_id)
        b1 = betting.encode_bet(actor=self.user_actor, encoded_by=self.user_id, device_id="TEST", match_id=match_id, side="WALA", amount=100)
        b2 = betting.encode_bet(actor=self.user_actor, encoded_by=self.user_id, device_id="TEST", match_id=match_id, side="MERON", amount=100)
        b3 = betting.encode_bet(actor=self.user_actor, encoded_by=self.user_id, device_id="TEST", match_id=match_id, side="DRAW", amount=10)
        betting.mark_printed(actor=self.user_actor, bet_id=int(b1["id"]))
        betting.mark_printed(actor=self.user_actor, bet_id=int(b2["id"]))
        betting.mark_printed(actor=self.user_actor, bet_id=int(b3["id"]))

        fight.set_result(actor=self.user_actor, match_id=match_id, result_type="DRAW", decided_by=self.user_id, notes=None)
        self.assertEqual(betting.compute_payout_for_slip(int(b1["id"])), 100)
        self.assertEqual(betting.compute_payout_for_slip(int(b2["id"])), 100)
        self.assertEqual(betting.compute_payout_for_slip(int(b3["id"])), 50)


if __name__ == "__main__":
    unittest.main()
