from __future__ import annotations

import argparse
import asyncio
import json


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="telegram-bot-testing-mcp",
        description="MCP server that tests Telegram bots as a real user "
                    "(default: run the stdio server)")
    sub = parser.add_subparsers(dest="cmd")
    login = sub.add_parser(
        "login",
        help="log in once: opens a QR window, or use --phone for headless "
             "terminal login (code is prompted on stdin)")
    login.add_argument("--timeout", type=int, default=300)
    login.add_argument("--phone", default=None,
                       help="phone number for headless login, e.g. +42077...")
    sub.add_parser("status", help="print mode and login status")
    args = parser.parse_args()

    if args.cmd == "login":
        from .config import Config
        from .session import BrowserSession

        async def run_phone(s: BrowserSession) -> None:
            res = await s.login_phone_start(args.phone)
            print(json.dumps(res), flush=True)
            if res["status"] == "already_logged_in":
                return
            code = input("Enter the confirmation code "
                         "(check your Telegram app or SMS): ")
            res = await s.login_submit_code(code)
            if res["status"] == "password_needed":
                import getpass
                res = await s.login_submit_password(
                    getpass.getpass("Two-factor password: "))
            print(json.dumps(res))

        async def run() -> None:
            s = BrowserSession(Config.from_env())
            try:
                if args.phone:
                    await run_phone(s)
                else:
                    print(json.dumps(await s.login_interactive(args.timeout)))
            except Exception as e:
                msg = str(e)
                if "XServer" in msg or "Target page, context or browser has been closed" in msg:
                    print(json.dumps({
                        "error": "no_display",
                        "message": "login opens a browser window and needs a display; "
                                   "this machine appears to be headless.",
                        "hint": "Log in on a desktop machine and copy the profile dir "
                                "(~/.telegram-user-mcp) here — see README 'Headless servers'.",
                    }))
                    raise SystemExit(1)
                raise
            finally:
                await s.stop()

        asyncio.run(run())
    elif args.cmd == "status":
        from .config import Config
        from .session import BrowserSession

        async def run() -> None:
            cfg = Config.from_env()
            s = BrowserSession(cfg)
            try:
                print(json.dumps({"mode": cfg.mode, "logged_in": await s.is_logged_in()}))
            finally:
                await s.stop()

        asyncio.run(run())
    else:
        from .server import mcp
        mcp.run()


if __name__ == "__main__":
    main()
