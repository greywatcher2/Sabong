PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  full_name TEXT,
  is_active INTEGER NOT NULL DEFAULT 1,
  is_frozen INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS roles (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  description TEXT
);

CREATE TABLE IF NOT EXISTS permissions (
  id INTEGER PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  description TEXT
);

CREATE TABLE IF NOT EXISTS role_permissions (
  role_id INTEGER NOT NULL REFERENCES roles(id),
  permission_id INTEGER NOT NULL REFERENCES permissions(id),
  PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE IF NOT EXISTS user_roles (
  user_id INTEGER NOT NULL REFERENCES users(id),
  role_id INTEGER NOT NULL REFERENCES roles(id),
  PRIMARY KEY (user_id, role_id)
);

CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  device_id TEXT NOT NULL,
  logged_in_at TEXT NOT NULL,
  last_seen_at TEXT,
  logged_out_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_sessions_active_user
ON sessions(user_id)
WHERE logged_out_at IS NULL;

CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY,
  actor_user_id INTEGER REFERENCES users(id),
  actor_device_id TEXT NOT NULL,
  action TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT,
  previous_state_json TEXT,
  new_state_json TEXT,
  metadata_json TEXT,
  created_at TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS audit_log_no_update
BEFORE UPDATE ON audit_log
BEGIN
  SELECT RAISE(ABORT, 'audit_log is append-only');
END;

CREATE TRIGGER IF NOT EXISTS audit_log_no_delete
BEFORE DELETE ON audit_log
BEGIN
  SELECT RAISE(ABORT, 'audit_log is append-only');
END;

CREATE TABLE IF NOT EXISTS fight_matches (
  id INTEGER PRIMARY KEY,
  match_number TEXT NOT NULL UNIQUE,
  fight_number INTEGER UNIQUE,
  structure_code TEXT NOT NULL,
  rounds INTEGER NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('DRAFT','LOCKED','ACTIVE','FINISHED','VOIDED')),
  locked_at TEXT,
  started_at TEXT,
  stopped_at TEXT,
  created_by INTEGER NOT NULL REFERENCES users(id),
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fight_structures (
  code TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  cocks_per_entry INTEGER NOT NULL CHECK (cocks_per_entry >= 1),
  default_rounds INTEGER NOT NULL CHECK (default_rounds >= 1),
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fight_matches_state ON fight_matches(state);

CREATE TABLE IF NOT EXISTS fight_entries (
  id INTEGER PRIMARY KEY,
  match_id INTEGER NOT NULL REFERENCES fight_matches(id),
  side TEXT NOT NULL CHECK (side IN ('WALA','MERON')),
  entry_name TEXT NOT NULL,
  owner TEXT NOT NULL,
  num_cocks INTEGER NOT NULL,
  weight_per_cock REAL NOT NULL,
  color TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  deleted_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_fight_entries_match_side ON fight_entries(match_id, side);

CREATE TABLE IF NOT EXISTS fight_results (
  match_id INTEGER PRIMARY KEY REFERENCES fight_matches(id),
  result_type TEXT NOT NULL CHECK (result_type IN ('WALA','MERON','DRAW','CANCELLED','NO_CONTEST')),
  decided_by INTEGER NOT NULL REFERENCES users(id),
  decided_at TEXT NOT NULL,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS bet_slips (
  id INTEGER PRIMARY KEY,
  slip_number TEXT NOT NULL UNIQUE,
  match_id INTEGER NOT NULL REFERENCES fight_matches(id),
  side TEXT NOT NULL CHECK (side IN ('WALA','MERON','DRAW')),
  amount INTEGER NOT NULL CHECK (amount >= 10),
  odds_snapshot_json TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('ENCODED','PRINTED','PAID','ARCHIVED','VOIDED','REFUNDED')),
  encoded_by INTEGER NOT NULL REFERENCES users(id),
  encoded_at TEXT NOT NULL,
  printed_at TEXT,
  payout_by INTEGER REFERENCES users(id),
  payout_at TEXT,
  payout_amount INTEGER,
  qr_payload TEXT NOT NULL UNIQUE,
  device_id TEXT NOT NULL,
  archived_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_bet_slips_match_side ON bet_slips(match_id, side);
CREATE INDEX IF NOT EXISTS idx_bet_slips_status ON bet_slips(status);

CREATE TABLE IF NOT EXISTS cash_drawers (
  id INTEGER PRIMARY KEY,
  drawer_type TEXT NOT NULL CHECK (drawer_type IN ('BETTING_CASHIER','CANTEEN')),
  name TEXT NOT NULL,
  owner_user_id INTEGER REFERENCES users(id),
  opened_at TEXT NOT NULL,
  closed_at TEXT,
  opening_cash INTEGER NOT NULL DEFAULT 0,
  current_cash INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_cash_drawers_type_owner ON cash_drawers(drawer_type, owner_user_id);

CREATE TABLE IF NOT EXISTS cash_movements (
  id INTEGER PRIMARY KEY,
  drawer_id INTEGER NOT NULL REFERENCES cash_drawers(id),
  movement_type TEXT NOT NULL CHECK (
    movement_type IN (
      'BET_IN',
      'PAYOUT_OUT',
      'REFUND_OUT',
      'ADJUSTMENT_IN',
      'ADJUSTMENT_OUT',
      'CANTEEN_SALE_IN',
      'STOCK_PURCHASE_OUT'
    )
  ),
  reference_type TEXT,
  reference_id TEXT,
  amount INTEGER NOT NULL CHECK (amount > 0),
  notes TEXT,
  created_by INTEGER NOT NULL REFERENCES users(id),
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cash_movements_drawer_created ON cash_movements(drawer_id, created_at);

CREATE TABLE IF NOT EXISTS canteen_items (
  id INTEGER PRIMARY KEY,
  sku TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  unit_price INTEGER NOT NULL CHECK (unit_price >= 0),
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS canteen_stock_movements (
  id INTEGER PRIMARY KEY,
  item_id INTEGER NOT NULL REFERENCES canteen_items(id),
  movement_type TEXT NOT NULL CHECK (movement_type IN ('IN','OUT','ADJUST')),
  qty INTEGER NOT NULL CHECK (qty > 0),
  unit_cost INTEGER CHECK (unit_cost >= 0),
  reference_type TEXT,
  reference_id TEXT,
  created_by INTEGER NOT NULL REFERENCES users(id),
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_canteen_stock_item_created ON canteen_stock_movements(item_id, created_at);

CREATE TABLE IF NOT EXISTS canteen_sales (
  id INTEGER PRIMARY KEY,
  receipt_number TEXT NOT NULL UNIQUE,
  drawer_id INTEGER NOT NULL REFERENCES cash_drawers(id),
  sold_by INTEGER NOT NULL REFERENCES users(id),
  sold_at TEXT NOT NULL,
  total_amount INTEGER NOT NULL CHECK (total_amount >= 0),
  status TEXT NOT NULL CHECK (status IN ('PAID','VOIDED'))
);

CREATE INDEX IF NOT EXISTS idx_canteen_sales_sold_at ON canteen_sales(sold_at);

CREATE TABLE IF NOT EXISTS canteen_sale_lines (
  id INTEGER PRIMARY KEY,
  sale_id INTEGER NOT NULL REFERENCES canteen_sales(id),
  item_id INTEGER NOT NULL REFERENCES canteen_items(id),
  qty INTEGER NOT NULL CHECK (qty > 0),
  unit_price INTEGER NOT NULL CHECK (unit_price >= 0),
  line_total INTEGER NOT NULL CHECK (line_total >= 0)
);

CREATE VIEW IF NOT EXISTS vw_bet_totals AS
SELECT
  match_id,
  SUM(CASE WHEN side = 'WALA' THEN amount ELSE 0 END) AS total_wala,
  SUM(CASE WHEN side = 'MERON' THEN amount ELSE 0 END) AS total_meron,
  SUM(CASE WHEN side = 'DRAW' THEN amount ELSE 0 END) AS total_draw,
  SUM(amount) AS total_all
FROM bet_slips
WHERE status IN ('ENCODED','PRINTED','PAID','ARCHIVED')
GROUP BY match_id;

CREATE TRIGGER IF NOT EXISTS trg_lock_match_on_first_bet
AFTER INSERT ON bet_slips
BEGIN
  UPDATE fight_matches
  SET locked_at = COALESCE(locked_at, NEW.encoded_at),
      state = CASE WHEN state = 'DRAFT' THEN 'LOCKED' ELSE state END
  WHERE id = NEW.match_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_prevent_entry_edit_after_lock
BEFORE UPDATE ON fight_entries
WHEN (SELECT locked_at IS NOT NULL FROM fight_matches WHERE id = NEW.match_id)
BEGIN
  SELECT RAISE(ABORT, 'Fight is locked; entries cannot be edited');
END;

CREATE TRIGGER IF NOT EXISTS trg_prevent_entry_delete_after_lock
BEFORE DELETE ON fight_entries
WHEN (SELECT locked_at IS NOT NULL FROM fight_matches WHERE id = OLD.match_id)
BEGIN
  SELECT RAISE(ABORT, 'Fight is locked; entries cannot be deleted');
END;
