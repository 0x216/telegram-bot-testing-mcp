import json

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from telegram_user_mcp.config import Config
from telegram_user_mcp.server import build_server

EXPECTED_TOOLS = {
    "tg_status", "tg_login", "tg_open_chat", "tg_send_message", "tg_send_file",
    "tg_read_messages", "tg_wait_for_message", "tg_click_button",
    "tg_click_reply_button", "tg_clear_chat", "tg_screenshot",
    "tg_miniapp_open", "tg_miniapp_snapshot", "tg_miniapp_click",
    "tg_miniapp_type", "tg_miniapp_screenshot", "tg_miniapp_close",
}


@pytest.fixture()
def server(tmp_path):
    cfg = Config.from_env({"TG_MCP_PROFILE_DIR": str(tmp_path / "profile")})
    return build_server(cfg)


async def test_all_tools_listed(server):
    async with create_connected_server_and_client_session(server._mcp_server) as client:
        tools = await client.list_tools()
        assert EXPECTED_TOOLS <= {t.name for t in tools.tools}


async def test_status_reports_mode_without_browser(server):
    async with create_connected_server_and_client_session(server._mcp_server) as client:
        res = await client.call_tool("tg_status", {})
        payload = json.loads(res.content[0].text)
        assert payload["mode"] == "prod"
        assert payload["logged_in"] is False
