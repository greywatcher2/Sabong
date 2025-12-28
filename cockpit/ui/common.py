from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
from tkinter import ttk


def show_error(parent: tk.Misc, title: str, exc: Exception | str) -> None:
    messagebox.showerror(title, str(exc), parent=parent)


def ask_text(parent: tk.Misc, title: str, prompt: str, initial: str = "") -> str | None:
    win = tk.Toplevel(parent)
    win.title(title)
    win.transient(parent)
    win.grab_set()
    win.configure(bg=_PALETTE["bg"])

    value = tk.StringVar(value=initial)

    shell = tk.Frame(win, bg=_PALETTE["bg"])
    shell.grid(row=0, column=0, sticky="nsew")
    shell.columnconfigure(0, weight=1)

    card_outer = tk.Frame(shell, bg=_PALETTE["shadow"])
    card_outer.grid(row=0, column=0, padx=16, pady=16, sticky="nsew")
    card = tk.Frame(card_outer, bg=_PALETTE["surface"])
    card.grid(row=0, column=0, padx=1, pady=1, sticky="nsew")
    card.columnconfigure(0, weight=1)

    ttk.Label(card, text=title, style="Title.TLabel").grid(row=0, column=0, padx=16, pady=(14, 2), sticky="w")
    ttk.Label(card, text=prompt, style="Body.TLabel").grid(row=1, column=0, padx=16, pady=(0, 10), sticky="w")
    entry = ttk.Entry(card, textvariable=value, width=46)
    entry.grid(row=2, column=0, padx=16, pady=(0, 14), sticky="we")
    entry.focus_set()

    result: list[str | None] = [None]

    def ok() -> None:
        result[0] = value.get().strip()
        win.destroy()

    def cancel() -> None:
        result[0] = None
        win.destroy()

    btns = ttk.Frame(card)
    btns.grid(row=3, column=0, padx=16, pady=(0, 16), sticky="e")
    ttk.Button(btns, text="Cancel", style="Secondary.TButton", command=cancel).pack(side="right", padx=(10, 0))
    ttk.Button(btns, text="OK", style="Primary.TButton", command=ok).pack(side="right")

    win.columnconfigure(0, weight=1)
    parent.wait_window(win)
    return result[0]


_PALETTE: dict[str, str] = {
    "bg": "#F6F3FF",
    "surface": "#FFFFFF",
    "surface2": "#FDFBFF",
    "text": "#252238",
    "muted": "#5A5672",
    "border": "#E7E1FF",
    "shadow": "#E6DFFF",
    "accent": "#7C5CFF",
    "accent_hover": "#6B4EF0",
    "accent_pressed": "#5A41DA",
    "success": "#34C8A1",
    "danger": "#FF6B8B",
    "warning": "#FFB84D",
    "select_bg": "#EDE7FF",
    "select_fg": "#252238",
}


def apply_theme(root: tk.Misc) -> None:
    root.configure(bg=_PALETTE["bg"])
    root.option_add("*Font", ("Segoe UI", 10))
    root.option_add("*Label.Font", ("Segoe UI", 10))
    root.option_add("*Button.Font", ("Segoe UI", 10))
    root.option_add("*Entry.Font", ("Segoe UI", 10))
    root.option_add("*Text.Font", ("Segoe UI", 10))

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    style.configure(
        ".",
        background=_PALETTE["bg"],
        foreground=_PALETTE["text"],
        bordercolor=_PALETTE["border"],
        lightcolor=_PALETTE["border"],
        darkcolor=_PALETTE["border"],
        troughcolor=_PALETTE["bg"],
        focuscolor=_PALETTE["accent"],
    )

    style.configure("TFrame", background=_PALETTE["bg"])
    style.configure("TLabel", background=_PALETTE["bg"], foreground=_PALETTE["text"])
    style.configure("Body.TLabel", background=_PALETTE["surface"], foreground=_PALETTE["text"])
    style.configure("Muted.TLabel", background=_PALETTE["surface"], foreground=_PALETTE["muted"])
    style.configure("Title.TLabel", background=_PALETTE["surface"], foreground=_PALETTE["text"], font=("Segoe UI", 16, "bold"))
    style.configure("ViewTitle.TLabel", background=_PALETTE["bg"], foreground=_PALETTE["text"], font=("Segoe UI", 16, "bold"))
    style.configure("SidebarUser.TLabel", background=_PALETTE["bg"], foreground=_PALETTE["text"], font=("Segoe UI", 11, "bold"))

    style.configure("Card.TFrame", background=_PALETTE["surface"])

    style.configure(
        "Primary.TButton",
        background=_PALETTE["accent"],
        foreground="#FFFFFF",
        padding=(14, 10),
        borderwidth=0,
        focusthickness=2,
        focuscolor=_PALETTE["accent"],
    )
    style.map(
        "Primary.TButton",
        background=[("active", _PALETTE["accent_hover"]), ("pressed", _PALETTE["accent_pressed"])],
        foreground=[("disabled", "#FFFFFF")],
    )

    style.configure(
        "Secondary.TButton",
        background=_PALETTE["surface"],
        foreground=_PALETTE["text"],
        padding=(14, 10),
        borderwidth=1,
        relief="flat",
    )
    style.map(
        "Secondary.TButton",
        background=[("active", _PALETTE["surface2"]), ("pressed", _PALETTE["select_bg"])],
    )

    style.configure(
        "Nav.TButton",
        background=_PALETTE["bg"],
        foreground=_PALETTE["text"],
        padding=(12, 10),
        borderwidth=0,
        relief="flat",
        anchor="w",
    )
    style.map(
        "Nav.TButton",
        background=[("active", _PALETTE["select_bg"]), ("pressed", _PALETTE["select_bg"])],
    )

    style.configure(
        "NavActive.TButton",
        background=_PALETTE["select_bg"],
        foreground=_PALETTE["text"],
        padding=(12, 10),
        borderwidth=0,
        relief="flat",
        anchor="w",
    )

    style.configure(
        "TEntry",
        fieldbackground=_PALETTE["surface"],
        background=_PALETTE["surface"],
        foreground=_PALETTE["text"],
        bordercolor=_PALETTE["border"],
        padding=(10, 8),
        relief="flat",
    )
    style.map(
        "TEntry",
        fieldbackground=[("disabled", _PALETTE["surface2"])],
        bordercolor=[("focus", _PALETTE["accent"]), ("active", _PALETTE["border"])],
    )

    style.configure(
        "TCombobox",
        fieldbackground=_PALETTE["surface"],
        background=_PALETTE["surface"],
        foreground=_PALETTE["text"],
        bordercolor=_PALETTE["border"],
        padding=(10, 8),
        relief="flat",
    )

    style.configure("TNotebook", background=_PALETTE["bg"], borderwidth=0)
    style.configure("TNotebook.Tab", padding=(14, 10), background=_PALETTE["bg"], foreground=_PALETTE["muted"])
    style.map(
        "TNotebook.Tab",
        background=[("selected", _PALETTE["surface"])],
        foreground=[("selected", _PALETTE["text"])],
    )

    style.configure("TSeparator", background=_PALETTE["border"])

    style.configure(
        "Treeview",
        background=_PALETTE["surface"],
        fieldbackground=_PALETTE["surface"],
        foreground=_PALETTE["text"],
        rowheight=30,
        bordercolor=_PALETTE["border"],
        lightcolor=_PALETTE["border"],
        darkcolor=_PALETTE["border"],
    )
    style.configure(
        "Treeview.Heading",
        background=_PALETTE["surface2"],
        foreground=_PALETTE["muted"],
        padding=(10, 8),
        relief="flat",
        font=("Segoe UI", 10, "bold"),
    )
    style.map(
        "Treeview",
        background=[("selected", _PALETTE["select_bg"])],
        foreground=[("selected", _PALETTE["select_fg"])],
    )


def palette() -> dict[str, str]:
    return dict(_PALETTE)
