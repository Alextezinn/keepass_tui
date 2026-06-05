"""Конфигурация приложения.

Хранится в ~/.config/keepass_cli/config.yaml.
При первом запуске создаётся автоматически.
"""

from __future__ import annotations
from typing import Any

from constants import CONFIG_PATH

try:
    import yaml  # type: ignore[import-untyped]
except ImportError:
    yaml = None


DEFAULTS: dict[str, Any] = {
    "password": {
        # Минимальная длина пароля — ниже этого значения показывается предупреждение
        "min_length": 12,
        # Длина генерируемого пароля при смене через SSH
        "generated_length": 20,
    }
}


def load() -> dict[str, Any]:
    """Загружает конфиг. Создаёт файл с дефолтами если не существует."""
    if yaml is None:
        return _deepcopy(DEFAULTS)

    if not CONFIG_PATH.exists():
        _create_default()
        return _deepcopy(DEFAULTS)

    try:
        raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        raw = {}

    return _merge(raw)


def save(cfg: dict[str, Any]) -> None:
    if yaml is None:
        return
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        yaml.dump(cfg, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


def is_weak(password: str, cfg: dict[str, Any]) -> bool:
    """True если длина пароля ниже минимума из конфига."""
    min_len = cfg.get("password", {}).get(
        "min_length", DEFAULTS["password"]["min_length"]
    )
    return len(password) < min_len


def min_length(cfg: dict[str, Any]) -> int:
    return cfg.get("password", {}).get("min_length", DEFAULTS["password"]["min_length"])


def generated_length(cfg: dict[str, Any]) -> int:
    return cfg.get("password", {}).get(
        "generated_length", DEFAULTS["password"]["generated_length"]
    )


# ── Внутренние ────────────────────────────────────────────────────────────────


def _deepcopy(d: dict) -> dict:
    import copy

    return copy.deepcopy(d)


def _merge(raw: dict) -> dict[str, Any]:
    result = _deepcopy(DEFAULTS)
    pw = raw.get("password", {})
    if isinstance(pw, dict):
        for key in ("min_length", "generated_length"):
            val = pw.get(key)
            if isinstance(val, int) and val > 0:
                result["password"][key] = val
    return result


def _create_default() -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        "# Конфигурация keepass-tui\n\n"
        "password:\n"
        "  # Минимальная длина пароля — ниже этого значения показывается предупреждение\n"
        "  min_length: 12\n"
        "  # Длина пароля при автоматической генерации (смена через SSH)\n"
        "  generated_length: 20\n",
        encoding="utf-8",
    )
