from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import tkinter as tk
from tkinter import messagebox

from cockpit.config import get_config
from cockpit.db.connection import connect, transaction
from cockpit.db.migrate import initialize_database
from cockpit.services.audit import Actor
from cockpit.services.auth import AuthService
from cockpit.services.operations import OperationsService
from cockpit.services.rbac import RBACService
from cockpit.ui.common import apply_theme
from cockpit.ui.public_display import PublicDisplayWindow
from cockpit.ui.setup_admin import SetupAdminWindow
from cockpit.ui.shell import ShellWindow
from cockpit.utils.device import get_device_id


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--viewer", action="store_true", help="Public display mode (no authentication)")
    return parser.parse_args(argv)


def _bootstrap(conn: sqlite3.Connection) -> None:
    initialize_database(conn)
    with transaction(conn):
        RBACService(conn).seed_defaults()


def run_app() -> None:
    args = _parse_args(sys.argv[1:])
    config = get_config()
    conn = connect(config.db_path)
    _bootstrap(conn)

    root = tk.Tk()
    root.title(config.app_name)
    root.geometry("1100x720")
    apply_theme(root)

    try:
        if args.viewer:
            PublicDisplayWindow(root=root, conn=conn).show()
        else:
            ops = OperationsService(conn)
            auth = AuthService(conn, ops.audit)
            with transaction(conn):
                auth.cleanup_stale_sessions(actor=Actor(user_id=None, device_id=get_device_id()))
            if auth.ensure_bootstrap_admin():
                SetupAdminWindow(root=root, ops=ops).show()
            else:
                ShellWindow(root=root, conn=conn).show()
        root.mainloop()
    except Exception as exc:
        messagebox.showerror("Fatal Error", str(exc))
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass
