from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    app_name: str = "Cockfight Management System"
    data_dir: Path = Path.home() / ".cockpit"
    db_path: Path = data_dir / "cockpit.sqlite3"


def get_config() -> AppConfig:
    config = AppConfig()
    config.data_dir.mkdir(parents=True, exist_ok=True)
    return config

