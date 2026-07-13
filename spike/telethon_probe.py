"""Diagnostic only: verify test-DC deterministic login directly (not the product path).

Connects to Telegram TEST DC 2, sends code for a 99966-number, tries code 22222.
"""
import asyncio
import random
import sys

from telethon import TelegramClient
from telethon.errors import (
    PhoneCodeInvalidError,
    PhoneNumberUnoccupiedError,
    SessionPasswordNeededError,
)
from telethon.sessions import StringSession

API_ID = 2496  # public webogram id from tweb source
API_HASH = "8da85b0d5bfe62527e5b244c209159c3"

DC = 2
TEST_DC_IP = "149.154.167.40"  # test DC2
PHONE = f"99966{DC}{random.randint(0, 9999):04d}"
CODE = str(DC) * 5


async def main():
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    client.session.set_dc(DC, TEST_DC_IP, 443)
    await client.connect()
    print("connected to", TEST_DC_IP)

    sent = await client.send_code_request(PHONE)
    print("sent_code:", type(sent.type).__name__, "len:", getattr(sent.type, "length", "?"))

    try:
        me = await client.sign_in(PHONE, code=CODE)
        print("SIGNED IN:", me.id, me.first_name)
    except PhoneNumberUnoccupiedError:
        print("number unoccupied -> signing up")
        me = await client.sign_up(code=CODE, first_name="Adapter", last_name="Spike")
        print("SIGNED UP:", me)
    except PhoneCodeInvalidError:
        print("PHONE_CODE_INVALID with", CODE)
    except SessionPasswordNeededError:
        print("2FA password set on this random number; retry with another YYYY")
    await client.disconnect()


print(f"phone={PHONE} code={CODE}")
asyncio.run(main())
