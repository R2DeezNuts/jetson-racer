import json
from pathlib import Path
from typing import Any, Dict, Optional


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_runtime_config(config_path: Optional[str] = None, config_dir: str = "socket_vision") -> Dict[str, Any]:
    if config_path:
        with Path(config_path).open("r", encoding="utf-8") as f:
            return json.load(f)

    root = Path(config_dir)
    config_files = [
        root / "conexion" / "config" / "default_config.json",
        root / "vision" / "config" / "default_config.json",
        root / "control" / "config" / "default_config.json",
        root / "global_config.json",
    ]
    cfg: Dict[str, Any] = {}
    for path in config_files:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as f:
            cfg = _deep_merge(cfg, json.load(f))
    return cfg
