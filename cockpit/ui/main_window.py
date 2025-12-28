from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import ttk

from cockpit.db.connection import transaction
from cockpit.services.audit import Actor
from cockpit.services.auth import AuthService, User
from cockpit.services.operations import OperationsService
from cockpit.ui.views.admin_users import AdminUsersView
from cockpit.ui.views.audit_log import AuditLogView
from cockpit.ui.views.canteen import CanteenView
from cockpit.ui.views.cashiering import CashieringView
from cockpit.ui.views.dashboard import DashboardView
from cockpit.ui.views.fight_registry import FightRegistryView
from cockpit.ui.views.fight_structures import FightStructuresView
from cockpit.ui.views.reports import ReportsView
from cockpit.ui.views.role_management import RoleManagementView


class MainWindow:
    def __init__(
        self,
        *,
        root: tk.Tk,
        conn: sqlite3.Connection,
        user: User,
        session_id: int,
        device_id: str,
        permissions: set[str],
    ) -> None:
        self._root = root
        self._conn = conn
        self._user = user
        self._session_id = session_id
        self._device_id = device_id
        self._perms = permissions

        self._ops = OperationsService(conn)
        self._auth = AuthService(conn, self._ops.audit)
        self._actor = Actor(user_id=user.id, device_id=device_id)

        bg = root.cget("bg")
        self._frame = tk.Frame(root, bg=bg)
        self._sidebar = tk.Frame(self._frame, width=240, padx=14, pady=14, bg=bg)
        self._content = tk.Frame(self._frame, padx=18, pady=18, bg=bg)
        self._active_view: tk.Widget | None = None
        self._nav_buttons: list[ttk.Button] = []
        self._heartbeat_after_id: str | None = None

    def show(self) -> None:
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._frame.pack(fill="both", expand=True)
        self._sidebar.pack(side="left", fill="y")
        self._content.pack(side="right", fill="both", expand=True)

        ttk.Label(self._sidebar, text=f"User: {self._user.username}", style="SidebarUser.TLabel").pack(anchor="w")
        ttk.Label(self._sidebar, text=" ", style="TLabel").pack()

        def add_nav(label: str, perm: str, factory) -> None:
            if perm in self._perms:
                btn = ttk.Button(self._sidebar, text=label, style="Nav.TButton", command=lambda: self._activate_and_show(btn, factory))
                btn.pack(fill="x", pady=5)
                self._nav_buttons.append(btn)

        add_nav("Dashboard", "VIEW_DASHBOARD", lambda parent: DashboardView(parent=parent, conn=self._conn))
        add_nav(
            "Fight Registry",
            "FIGHT_REGISTER",
            lambda parent: FightRegistryView(parent=parent, conn=self._conn, actor=self._actor, permissions=self._perms),
        )
        add_nav("Fight Structures", "ADMIN_ALL", lambda parent: FightStructuresView(parent=parent, conn=self._conn, actor=self._actor))
        add_nav("Cashiering / Betting", "BET_ENCODE", lambda parent: CashieringView(parent=parent, conn=self._conn, actor=self._actor, user_id=self._user.id, device_id=self._device_id))
        add_nav("Canteen", "CANTEEN_POS", lambda parent: CanteenView(parent=parent, conn=self._conn, actor=self._actor, user_id=self._user.id))
        add_nav("Roles & Permissions", "ROLE_MANAGE", lambda parent: RoleManagementView(parent=parent, conn=self._conn, actor=self._actor))
        add_nav("Reports", "VIEW_REPORTS", lambda parent: ReportsView(parent=parent, conn=self._conn))
        add_nav("Audit Log", "VIEW_AUDIT_LOG", lambda parent: AuditLogView(parent=parent, conn=self._conn))
        add_nav("User Management", "USER_MANAGE", lambda parent: AdminUsersView(parent=parent, conn=self._conn, actor=self._actor))

        ttk.Separator(self._sidebar).pack(fill="x", pady=14)
        ttk.Button(self._sidebar, text="Logout", style="Secondary.TButton", command=self._logout).pack(fill="x")

        if "VIEW_DASHBOARD" in self._perms:
            self._activate_and_show(self._nav_buttons[0] if self._nav_buttons else None, lambda parent: DashboardView(parent=parent, conn=self._conn))
        elif "FIGHT_REGISTER" in self._perms:
            self._activate_and_show(self._nav_buttons[0] if self._nav_buttons else None, lambda parent: FightRegistryView(parent=parent, conn=self._conn, actor=self._actor, permissions=self._perms))
        elif "BET_ENCODE" in self._perms:
            self._activate_and_show(
                self._nav_buttons[0] if self._nav_buttons else None,
                lambda parent: CashieringView(parent=parent, conn=self._conn, actor=self._actor, user_id=self._user.id, device_id=self._device_id),
            )
        self._schedule_heartbeat()

    def _on_close(self) -> None:
        if self._heartbeat_after_id is not None:
            try:
                self._root.after_cancel(self._heartbeat_after_id)
            except Exception:
                pass
            self._heartbeat_after_id = None
        try:
            with transaction(self._conn):
                self._auth.logout(actor=self._actor, session_id=self._session_id)
        except Exception:
            pass
        self._root.destroy()

    def _schedule_heartbeat(self) -> None:
        try:
            self._auth.heartbeat(session_id=self._session_id)
        except Exception:
            pass
        try:
            self._heartbeat_after_id = self._root.after(10000, self._schedule_heartbeat)
        except Exception:
            self._heartbeat_after_id = None

    def _activate_and_show(self, btn: ttk.Button | None, factory) -> None:
        for b in self._nav_buttons:
            b.configure(style="Nav.TButton")
        if btn is not None:
            btn.configure(style="NavActive.TButton")
        self._show(factory)

    def _show(self, factory) -> None:
        if self._active_view is not None:
            self._active_view.destroy()
            self._active_view = None
        self._active_view = factory(self._content)
        self._active_view.pack(fill="both", expand=True)

    def _logout(self) -> None:
        if self._heartbeat_after_id is not None:
            try:
                self._root.after_cancel(self._heartbeat_after_id)
            except Exception:
                pass
            self._heartbeat_after_id = None
        with transaction(self._conn):
            self._auth.logout(actor=self._actor, session_id=self._session_id)
        self._frame.destroy()
        from cockpit.ui.login import LoginWindow

        LoginWindow(root=self._root, conn=self._conn).show()
