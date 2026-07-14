from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from telegram_user_mcp import extract

FIXTURE = (Path(__file__).parent / "fixtures" / "bubbles.html").read_text(encoding="utf-8")


@pytest.fixture()
async def page():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        pg = await browser.new_page()
        await pg.set_content(FIXTURE)
        yield pg
        await browser.close()


async def test_reads_text_and_direction(page):
    msgs = await extract.read_messages(page)
    incoming = [m for m in msgs if not m.out and not m.service]
    outgoing = [m for m in msgs if m.out]
    assert incoming and outgoing
    assert incoming[0].text.startswith("fixture bot ready")
    assert "19:01" not in incoming[0].text  # time stripped from text
    assert incoming[0].time == "19:01"
    # emoji render as <img> in WebK; extraction must keep them via alt text
    assert outgoing[0].text == "hello bot 🥛"
    assert isinstance(incoming[0].id, int) and incoming[0].id == 101


async def test_reads_inline_keyboard_grid(page):
    msgs = await extract.read_messages(page)
    with_buttons = [m for m in msgs if m.buttons]
    assert with_buttons, "fixture has a 2x2 keyboard"
    grid = with_buttons[0].buttons
    assert grid == [["A1", "A2"], ["B1", "B2"]]


async def test_detects_service_and_media(page):
    msgs = await extract.read_messages(page)
    assert any(m.service for m in msgs)
    assert any(m.media == "photo" for m in msgs)


async def test_limit(page):
    msgs = await extract.read_messages(page, limit=1)
    assert len(msgs) == 1
    assert msgs[0].id == 103


async def test_reply_attribution(page):
    msgs = await extract.read_messages(page)
    reply = next(m for m in msgs if m.id == 110)
    assert reply.reply_to == {"title": "MCP Fixture Bot", "quote": "reply target"}
    assert reply.text == "this replies to the target"


async def test_forward_attribution(page):
    msgs = await extract.read_messages(page)
    fwd = next(m for m in msgs if m.id == 111)
    assert fwd.forwarded_from == "MCP Fixture Bot"
    assert fwd.sender is None
    assert fwd.text == "forward source"


async def test_location_contact_poll_detection(page):
    msgs = await extract.read_messages(page)
    by_id = {m.id: m for m in msgs}
    assert by_id[112].media == "location"
    assert by_id[113].media == "contact"
    assert "Fixture Contact" in by_id[113].text
    assert by_id[114].media == "poll"
    assert by_id[114].poll == {"question": "favorite color?",
                               "options": ["Red", "Green", "Blue"]}
    assert by_id[103].media == "photo"  # geo detection must not shadow photos
