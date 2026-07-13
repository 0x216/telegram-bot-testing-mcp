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
