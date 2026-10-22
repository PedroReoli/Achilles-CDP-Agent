"""Comandos estruturados para sessões nomeadas."""

import asyncio
import json
from pathlib import Path
from typing import Optional

from achilles.services.chrome_launcher import cdp_available, ensure_chrome_running
from achilles.services.errors import ServiceError
from achilles.services.named_sessions import NamedSessionRegistry


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


async def _stop_browser(port: int) -> bool:
    if not cdp_available(port):
        return False
    from playwright.async_api import async_playwright

    owner = await async_playwright().start()
    try:
        browser = await owner.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        session = await browser.new_browser_cdp_session()
        await session.send("Browser.close")
        for _ in range(30):
            if not cdp_available(port):
                return True
            await asyncio.sleep(0.1)
        return not cdp_available(port)
    finally:
        await owner.stop()


def run_session(
    operation: str,
    name: Optional[str] = None,
    port: Optional[int] = None,
    browser: str = "chrome",
) -> None:
    registry = NamedSessionRegistry()
    try:
        if operation == "create":
            record = registry.create(name or "", port, browser)
            _emit({"ok": True, "session": record})
            return
        if operation == "list":
            result = registry.list()
            for item in result["sessions"]:
                item["running"] = cdp_available(int(item["cdp_port"]))
            _emit({"ok": True, **result})
            return
        if operation == "use":
            _emit({"ok": True, "session": registry.use(name or "")})
            return
        if operation == "remove":
            _emit({"ok": True, **registry.remove(name or "")})
            return
        record = registry.get(name)
        if operation == "status":
            _emit({"ok": True, "session": record, "running": cdp_available(record["cdp_port"])})
            return
        if operation == "start":
            started = ensure_chrome_running(
                int(record["cdp_port"]),
                custom_profile_dir=Path(record["profile_dir"]),
                browser=record["browser"],
            )
            if not started:
                raise ServiceError("CDP_UNAVAILABLE", "O navegador da sessão não iniciou.")
            registry.use(record["name"])
            _emit({"ok": True, "session": record, "running": True})
            return
        if operation == "stop":
            stopped = asyncio.run(_stop_browser(int(record["cdp_port"])))
            _emit({"ok": True, "session": record, "stopped": stopped})
            return
        raise ServiceError("INVALID_ARGUMENT", "Operação de sessão desconhecida.")
    except ServiceError as exc:
        _emit({"ok": False, "error": exc.as_dict()})
        raise SystemExit(1) from None
