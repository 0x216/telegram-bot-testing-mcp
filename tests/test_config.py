from pathlib import Path

import pytest

from telegram_user_mcp.config import Config, DEFAULT_ROOT


def test_defaults():
    cfg = Config.from_env({})
    assert cfg.mode == "prod"
    assert cfg.headed is False
    assert cfg.profile_dir == DEFAULT_ROOT / "profile-prod"
    assert cfg.base_url == "https://web.telegram.org/k/"


def test_test_mode_url_and_profile():
    cfg = Config.from_env({"TG_MCP_MODE": "test"})
    assert cfg.base_url == "https://web.telegram.org/k/?test=1"
    assert cfg.profile_dir == DEFAULT_ROOT / "profile-test"


def test_overrides():
    cfg = Config.from_env({
        "TG_MCP_MODE": "prod",
        "TG_MCP_HEADED": "1",
        "TG_MCP_PROFILE_DIR": "C:/tmp/prof",
    })
    assert cfg.headed is True
    assert cfg.profile_dir == Path("C:/tmp/prof")


def test_invalid_mode_rejected():
    with pytest.raises(ValueError):
        Config.from_env({"TG_MCP_MODE": "staging"})
