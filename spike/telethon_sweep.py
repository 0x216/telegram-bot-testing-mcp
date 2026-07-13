"""Sweep test DCs / api creds / code variants to find what the test server accepts."""
import asyncio
import random

from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    PhoneCodeInvalidError,
    PhoneNumberUnoccupiedError,
    SessionPasswordNeededError,
)
from telethon.sessions import StringSession

TEST_DCS = {1: "149.154.175.10", 2: "149.154.167.40", 3: "149.154.175.117"}
API_CREDS = [
    (2496, "8da85b0d5bfe62527e5b244c209159c3", "webk"),
    (17349, "344583e45741c457fe1862106095a5eb", "tdesktop-test"),
]


async def try_one(dc, api_id, api_hash, label):
    phone = f"99966{dc}{random.randint(0, 9999):04d}"
    client = TelegramClient(StringSession(), api_id, api_hash)
    client.session.set_dc(dc, TEST_DCS[dc], 443)
    try:
        await client.connect()
        sent = await client.send_code_request(phone)
        stype = type(sent.type).__name__
        for code in (str(dc) * 5, str(dc) * 6):
            try:
                me = await client.sign_in(phone, code=code)
                print(f"  OK  dc{dc} {label} {phone} code={code} -> signed in {me.id}")
                return True
            except PhoneNumberUnoccupiedError:
                print(f"  OK* dc{dc} {label} {phone} code={code} -> UNOCCUPIED (code accepted!)")
                me = await client.sign_up(code=code, first_name="Adapter", last_name="Spike")
                print(f"      signed up -> {getattr(me, 'id', me)}")
                return True
            except PhoneCodeInvalidError:
                print(f"  --  dc{dc} {label} {phone} sent={stype} code={code} invalid")
            except SessionPasswordNeededError:
                print(f"  2FA dc{dc} {label} {phone} code={code} accepted but 2FA set")
                return True
    except FloodWaitError as e:
        print(f"  FLOOD dc{dc} {label}: wait {e.seconds}s")
    except Exception as e:
        print(f"  ERR dc{dc} {label}: {type(e).__name__}: {e}")
    finally:
        await client.disconnect()
    return False


async def main():
    for dc in (1, 2, 3):
        for api_id, api_hash, label in API_CREDS:
            if await try_one(dc, api_id, api_hash, label):
                return


asyncio.run(main())
