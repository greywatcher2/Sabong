from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import ttk


class ReportsView(tk.Frame):
    def __init__(self, *, parent: tk.Misc, conn: sqlite3.Connection) -> None:
        bg = parent.cget("bg")
        super().__init__(parent, bg=bg)
        self._conn = conn

        ttk.Label(self, text="Reports", style="ViewTitle.TLabel").pack(anchor="w", pady=(0, 12))

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)

        self._fight_history = _TableTab(nb, conn=conn, title="Fight History")
        self._daily_income = _TableTab(nb, conn=conn, title="Daily Income")
        self._cashier_perf = _TableTab(nb, conn=conn, title="Cashier Performance")
        self._canteen_sales = _TableTab(nb, conn=conn, title="Canteen Sales")

        nb.add(self._fight_history, text="Fight History")
        nb.add(self._daily_income, text="Daily Income")
        nb.add(self._cashier_perf, text="Cashiers")
        nb.add(self._canteen_sales, text="Canteen")

        self._refresh()

    def _refresh(self) -> None:
        self._fight_history.set_query(
            columns=("match_number", "state", "result", "decided_at"),
            headings=("Match #", "State", "Result", "Decided At"),
            query="""
              SELECT fm.match_number, fm.state, COALESCE(fr.result_type, '') AS result, COALESCE(fr.decided_at, '') AS decided_at
              FROM fight_matches fm
              LEFT JOIN fight_results fr ON fr.match_id = fm.id
              ORDER BY fm.id DESC
              LIMIT 200
            """,
        )

        self._daily_income.set_query(
            columns=("day", "bet_in", "bet_payouts", "bet_net", "canteen_sales"),
            headings=("Day", "Bet In", "Bet Payouts", "Bet Net", "Canteen Sales"),
            query="""
              WITH bet AS (
                SELECT
                  substr(COALESCE(payout_at, encoded_at), 1, 10) AS day,
                  SUM(amount) AS bet_in,
                  SUM(COALESCE(payout_amount, 0)) AS bet_payouts
                FROM bet_slips
                WHERE status IN ('PAID','ARCHIVED','PRINTED','ENCODED')
                GROUP BY substr(COALESCE(payout_at, encoded_at), 1, 10)
              ),
              canteen AS (
                SELECT substr(sold_at, 1, 10) AS day, SUM(total_amount) AS sales
                FROM canteen_sales
                WHERE status = 'PAID'
                GROUP BY substr(sold_at, 1, 10)
              )
              SELECT
                COALESCE(bet.day, canteen.day) AS day,
                COALESCE(bet.bet_in, 0) AS bet_in,
                COALESCE(bet.bet_payouts, 0) AS bet_payouts,
                COALESCE(bet.bet_in, 0) - COALESCE(bet.bet_payouts, 0) AS bet_net,
                COALESCE(canteen.sales, 0) AS canteen_sales
              FROM bet
              FULL OUTER JOIN canteen ON canteen.day = bet.day
            """,
        )

        self._cashier_perf.set_query(
            columns=("cashier", "bets_count", "bet_in", "payouts"),
            headings=("Cashier", "Bets", "Bet In", "Payouts"),
            query="""
              SELECT
                u.username AS cashier,
                COUNT(b.id) AS bets_count,
                SUM(b.amount) AS bet_in,
                SUM(COALESCE(b.payout_amount, 0)) AS payouts
              FROM bet_slips b
              JOIN users u ON u.id = b.encoded_by
              GROUP BY u.username
              ORDER BY bet_in DESC
              LIMIT 100
            """,
        )

        self._canteen_sales.set_query(
            columns=("seller", "sales_count", "sales_total"),
            headings=("Seller", "Sales", "Total"),
            query="""
              SELECT
                u.username AS seller,
                COUNT(s.id) AS sales_count,
                SUM(s.total_amount) AS sales_total
              FROM canteen_sales s
              JOIN users u ON u.id = s.sold_by
              WHERE s.status = 'PAID'
              GROUP BY u.username
              ORDER BY sales_total DESC
              LIMIT 100
            """,
        )

        self._fight_history.refresh()
        self._daily_income.refresh()
        self._cashier_perf.refresh()
        self._canteen_sales.refresh()


class _TableTab(tk.Frame):
    def __init__(self, parent: ttk.Notebook, *, conn: sqlite3.Connection, title: str) -> None:
        super().__init__(parent, bg=parent.winfo_toplevel().cget("bg"))
        self._conn = conn
        self._title = title
        self._query = ""
        self._columns: tuple[str, ...] = ()

        self._tree = ttk.Treeview(self, columns=(), show="headings", height=18)
        self._tree.pack(fill="both", expand=True, padx=8, pady=8)
        ttk.Button(self, text="Refresh", style="Secondary.TButton", command=self.refresh).pack(anchor="e", padx=8, pady=(0, 8))

    def set_query(self, *, columns: tuple[str, ...], headings: tuple[str, ...], query: str) -> None:
        self._columns = columns
        self._query = query
        self._tree.configure(columns=columns)
        for c, h in zip(columns, headings, strict=False):
            self._tree.heading(c, text=h)
            self._tree.column(c, width=160, anchor="center")

    def refresh(self) -> None:
        for i in self._tree.get_children():
            self._tree.delete(i)
        if not self._query:
            return

        query = self._query
        if "FULL OUTER JOIN" in query:
            query = """
              WITH bet AS (
                SELECT
                  substr(COALESCE(payout_at, encoded_at), 1, 10) AS day,
                  SUM(amount) AS bet_in,
                  SUM(COALESCE(payout_amount, 0)) AS bet_payouts
                FROM bet_slips
                WHERE status IN ('PAID','ARCHIVED','PRINTED','ENCODED')
                GROUP BY substr(COALESCE(payout_at, encoded_at), 1, 10)
              ),
              canteen AS (
                SELECT substr(sold_at, 1, 10) AS day, SUM(total_amount) AS sales
                FROM canteen_sales
                WHERE status = 'PAID'
                GROUP BY substr(sold_at, 1, 10)
              ),
              days AS (
                SELECT day FROM bet
                UNION
                SELECT day FROM canteen
              )
              SELECT
                d.day AS day,
                COALESCE(b.bet_in, 0) AS bet_in,
                COALESCE(b.bet_payouts, 0) AS bet_payouts,
                COALESCE(b.bet_in, 0) - COALESCE(b.bet_payouts, 0) AS bet_net,
                COALESCE(c.sales, 0) AS canteen_sales
              FROM days d
              LEFT JOIN bet b ON b.day = d.day
              LEFT JOIN canteen c ON c.day = d.day
              ORDER BY d.day DESC
              LIMIT 60
            """

        rows = self._conn.execute(query).fetchall()
        for r in rows:
            self._tree.insert("", "end", values=tuple(r[c] for c in self._columns))
