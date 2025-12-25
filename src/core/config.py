from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

_SETTINGS = None


def load_env() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    env_path = repo_root / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()


def _resolve_config_path() -> Path:
    raw_path = os.getenv("RAG_CONFIG_PATH", "config.json")
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = (Path(__file__).resolve().parents[2] / path).resolve()
    return path


def load_settings() -> dict:
    global _SETTINGS
    if _SETTINGS is not None:
        return _SETTINGS

    load_env()
    config_path = _resolve_config_path()
    if not config_path.exists():
        raise FileNotFoundError(
            "Config file not found. Copy config.example.json to config.json and update it."
        )
    _SETTINGS = json.loads(config_path.read_text())
    return _SETTINGS


def get_setting(key: str, *, default=None, required: bool = False):
    settings = load_settings()
    if key in settings:
        return settings[key]
    if required:
        raise KeyError(f"Missing required config key: {key}")
    return default
