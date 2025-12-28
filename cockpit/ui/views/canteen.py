from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import ttk

from cockpit.db.connection import transaction
from cockpit.services.audit import Actor
from cockpit.services.canteen import CanteenService
from cockpit.services.operations import OperationsService
from cockpit.ui.common import ask_text, show_error
from cockpit.ui.common import palette


class _CanteenPublicWindow(tk.Toplevel):
    def __init__(self, *, parent: tk.Misc, conn: sqlite3.Connection) -> None:
        super().__init__(parent)
        self.title("Canteen Public Display")
        self.geometry("720x520")
        self.configure(bg="black")
        self._conn = conn
        self._svc = CanteenService(conn, audit=None)

        self._title = tk.Label(self, text="CANTEEN MENU", fg="white", bg="black", font=("Segoe UI", 22, "bold"))
        self._title.pack(anchor="w", padx=16, pady=(16, 10))

        self._text = tk.Text(self, bg="black", fg="white", font=("Consolas", 16), bd=0)
        self._text.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self._text.configure(state="disabled")
        self._refresh()

    def _refresh(self) -> None:
        items = self._svc.list_items()
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        for it in items:
            self._text.insert("end", f"{it.name:<28}  ₱{it.unit_price}\n")
        self._text.configure(state="disabled")
        self.after(1500, self._refresh)


class CanteenView(tk.Frame):
    def __init__(self, *, parent: tk.Misc, conn: sqlite3.Connection, actor: Actor, user_id: int) -> None:
        bg = parent.cget("bg")
        super().__init__(parent, bg=bg)
        self._conn = conn
        self._actor = actor
        self._user_id = user_id
        self._ops = OperationsService(conn)
        self._svc = CanteenService(conn, self._ops.audit)

        ttk.Label(self, text="Canteen POS", style="ViewTitle.TLabel").grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 12))

        ttk.Button(self, text="Open Public Display (2nd Screen)", style="Secondary.TButton", command=self._open_public).grid(row=1, column=0, sticky="w")
        ttk.Button(self, text="Add/Update Item", style="Secondary.TButton", command=self._add_item).grid(row=1, column=1, sticky="w", padx=(10, 0))
        ttk.Button(self, text="Stock In", style="Secondary.TButton", command=self._stock_in).grid(row=1, column=2, sticky="w", padx=(10, 0))

        self._items = ttk.Treeview(self, columns=("sku", "name", "price", "stock"), show="headings", height=10)
        for col, title, w in (("sku", "SKU", 100), ("name", "Name", 240), ("price", "Price", 90), ("stock", "Stock", 90)):
            self._items.heading(col, text=title)
            self._items.column(col, width=w, anchor="center")
        self._items.grid(row=2, column=0, columnspan=4, sticky="nsew", pady=(10, 0))

        ttk.Separator(self).grid(row=3, column=0, columnspan=4, sticky="ew", pady=14)
        ttk.Label(self, text="Quick Sale", style="TLabel").grid(row=4, column=0, sticky="w")
        ttk.Button(self, text="New Sale", style="Primary.TButton", command=self._new_sale).grid(row=4, column=1, sticky="w")

        p = palette()
        self._sale_log = tk.Text(self, height=8, bg=p["surface"], fg=p["text"], highlightthickness=1, highlightbackground=p["border"], bd=0)
        self._sale_log.grid(row=5, column=0, columnspan=4, sticky="nsew", pady=(10, 0))
        self.rowconfigure(5, weight=1)
        for c in range(4):
            self.columnconfigure(c, weight=1)
        self.rowconfigure(2, weight=1)

        self._public: _CanteenPublicWindow | None = None
        self._refresh()

    def _open_public(self) -> None:
        if self._public is None or not self._public.winfo_exists():
            self._public = _CanteenPublicWindow(parent=self, conn=self._conn)
        else:
            self._public.lift()

    def _refresh(self) -> None:
        for i in self._items.get_children():
            self._items.delete(i)
        items = self._svc.list_items()
        for it in items:
            stock = self._svc.current_stock(it.id)
            self._items.insert("", "end", text=str(it.id), values=(it.sku, it.name, f"₱{it.unit_price}", stock))
        self.after(1500, self._refresh)

    def _selected_item_id(self) -> int | None:
        sel = self._items.selection()
        if not sel:
            return None
        return int(self._items.item(sel[0], "text"))

    def _add_item(self) -> None:
        sku = ask_text(self, "Item", "SKU:")
        if not sku:
            return
        name = ask_text(self, "Item", "Name:")
        price_s = ask_text(self, "Item", "Unit price (₱):", initial="0")
        if not name or price_s is None:
            return
        try:
            with transaction(self._conn):
                self._svc.upsert_item(actor=self._actor, sku=sku.strip().upper(), name=name.strip(), unit_price=int(price_s), created_by=self._user_id)
        except Exception as exc:
            show_error(self, "Item", exc)

    def _stock_in(self) -> None:
        item_id = self._selected_item_id()
        if item_id is None:
            show_error(self, "Stock In", "Select an item first")
            return
        qty_s = ask_text(self, "Stock In", "Quantity:", initial="1")
        cost_s = ask_text(self, "Stock In", "Unit cost (optional):", initial="")
        if not qty_s:
            return
        try:
            unit_cost = int(cost_s) if cost_s and cost_s.strip() else None
            with transaction(self._conn):
                self._svc.stock_in(actor=self._actor, created_by=self._user_id, item_id=item_id, qty=int(qty_s), unit_cost=unit_cost, notes=None)
        except Exception as exc:
            show_error(self, "Stock In", exc)

    def _new_sale(self) -> None:
        item_id = self._selected_item_id()
        if item_id is None:
            show_error(self, "Sale", "Select an item first")
            return
        qty_s = ask_text(self, "Sale", "Quantity:", initial="1")
        if not qty_s:
            return
        try:
            with transaction(self._conn):
                sale = self._ops.canteen_sale_with_cash(
                    actor=self._actor,
                    canteen_user_id=self._user_id,
                    drawer_id=None,
                    lines=[{"item_id": item_id, "qty": int(qty_s)}],
                )
            self._sale_log.insert("end", f"SALE {sale['receipt_number']} | ₱{sale['total_amount']}\n")
            self._sale_log.see("end")
        except Exception as exc:
            show_error(self, "Sale", exc)
