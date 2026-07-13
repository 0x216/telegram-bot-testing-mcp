from telegram_user_mcp.errors import AdapterError, ButtonNotFound, NotLoggedIn


def test_payload_shape():
    e = ButtonNotFound("Pay", ["Start", "Help"])
    p = e.to_payload()
    assert p["error"] == "button_not_found"
    assert p["available_buttons"] == ["Start", "Help"]
    assert "Pay" in p["message"]
    assert p["hint"]


def test_not_logged_in_hint_mentions_login():
    assert "tg_login" in NotLoggedIn().to_payload()["hint"]


def test_all_are_adapter_errors():
    assert issubclass(ButtonNotFound, AdapterError)
