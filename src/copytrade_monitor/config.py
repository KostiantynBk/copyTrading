from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, Field

from .models import Profile


class Settings(BaseModel):
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    poll_interval_seconds: int = 45
    lookback_hours: int = 72
    headless: bool = True
    x_browser_channel: str = "msedge"
    x_navigation_timeout_ms: int = 45000
    x_post_load_wait_ms: int = 2500
    x_debug: bool = False
    x_storage_state_path: Path = Path("playwright_state.json")
    profiles_path: Path = Path("profiles.json")
    data_dir: Path = Path("data")

    @property
    def cache_path(self) -> Path:
        return self.data_dir / "cache.json"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def analyses_path(self) -> Path:
        return self.data_dir / "analyses.jsonl"


def _read_env_file(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _discover_base_dir(cwd: Path, module_path: Path) -> Path:
    search_roots = [cwd.resolve()]
    resolved_module = module_path.resolve()
    search_roots.extend(parent for parent in resolved_module.parents)

    seen: set[Path] = set()
    for root in search_roots:
        if root in seen:
            continue
        seen.add(root)
        for candidate in [root, *root.parents]:
            if (candidate / ".env").exists() or (candidate / "profiles.json").exists():
                return candidate
            if (candidate / "pyproject.toml").exists() and (candidate / "src").exists():
                return candidate
    return cwd.resolve()


def load_settings(base_dir: Path | None = None, require_api_key: bool = True) -> Settings:
    base = base_dir or _discover_base_dir(Path.cwd(), Path(__file__))
    env_values = _read_env_file(base / ".env")

    def get(name: str, default: str | None = None) -> str | None:
        return os.getenv(name, env_values.get(name, default))

    api_key = get("OPENAI_API_KEY")
    if require_api_key and not api_key:
        raise ValueError("OPENAI_API_KEY is required. Set it in .env or the environment.")

    headless_raw = (get("HEADLESS", "true") or "true").strip().lower()
    x_debug_raw = (get("X_DEBUG", "false") or "false").strip().lower()
    return Settings(
        openai_api_key=api_key,
        openai_model=get("OPENAI_MODEL", "gpt-4.1-mini") or "gpt-4.1-mini",
        poll_interval_seconds=int(get("POLL_INTERVAL_SECONDS", "45") or "45"),
        lookback_hours=int(get("LOOKBACK_HOURS", "72") or "72"),
        headless=headless_raw in {"1", "true", "yes", "on"},
        x_browser_channel=(get("X_BROWSER_CHANNEL", "msedge") or "msedge").strip(),
        x_navigation_timeout_ms=int(get("X_NAVIGATION_TIMEOUT_MS", "45000") or "45000"),
        x_post_load_wait_ms=int(get("X_POST_LOAD_WAIT_MS", "2500") or "2500"),
        x_debug=x_debug_raw in {"1", "true", "yes", "on"},
        x_storage_state_path=base / (get("X_STORAGE_STATE_PATH", "playwright_state.json") or "playwright_state.json"),
        profiles_path=base / (get("PROFILES_PATH", "profiles.json") or "profiles.json"),
        data_dir=base / (get("DATA_DIR", "data") or "data"),
    )


def load_profiles(path: Path) -> list[Profile]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [Profile.model_validate(item) for item in raw]
