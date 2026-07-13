from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

DEFAULT_ROOT = Path.home() / ".telegram-user-mcp"
_WEBK = "https://web.telegram.org/k/"


@dataclass(frozen=True)
class Config:
    mode: str = "prod"
    headed: bool = False
    profile_dir: Path = DEFAULT_ROOT / "profile-prod"

    @staticmethod
    def from_env(env: Mapping[str, str] | None = None) -> "Config":
        env = os.environ if env is None else env
        mode = env.get("TG_MCP_MODE", "prod").lower()
        if mode not in ("prod", "test"):
            raise ValueError(f"TG_MCP_MODE must be 'prod' or 'test', got {mode!r}")
        headed = env.get("TG_MCP_HEADED", "") in ("1", "true", "yes")
        profile = env.get("TG_MCP_PROFILE_DIR")
        profile_dir = Path(profile) if profile else DEFAULT_ROOT / f"profile-{mode}"
        return Config(mode=mode, headed=headed, profile_dir=profile_dir)

    @property
    def base_url(self) -> str:
        return _WEBK + ("?test=1" if self.mode == "test" else "")
