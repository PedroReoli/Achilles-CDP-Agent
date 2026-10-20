"""Ações com Locators nativos e resultado Observe → Act → Verify."""

import asyncio
import time
from typing import Any, Dict, Optional

from .errors import ServiceError
from .hud import HudManager
from .observation_engine import ObservationEngine
from .redaction import redact_url
from .session_manager import BrowserSessionManager


class ActionResolver:
    def __init__(self, session: BrowserSessionManager, observations: ObservationEngine) -> None:
        self.session = session
        self.observations = observations

    async def execute(
        self,
        action: str,
        snapshot_id: str,
        element_ref: str,
        page_id: str,
        value: Optional[str] = None,
        timeout_ms: int = 5000,
        verify: str = "target",
    ) -> Dict[str, Any]:
        started = time.perf_counter()
        if action not in ("click", "fill", "hover", "press", "select"):
            raise ServiceError("INVALID_ARGUMENT", "Ação inválida.")
        if action in ("fill", "press", "select") and value is None:
            raise ServiceError("INVALID_ARGUMENT", "A ação exige value.")
        key, page = await self.session.page(page_id)
        url_before = redact_url(page.url)
        async with self.session.registry.locks[key]:
            target = self.observations.target(snapshot_id, element_ref, key)
            frame = self.session.registry.frames.get(target["frame_id"])
            if frame is None or frame.is_detached():
                raise ServiceError("STALE_ELEMENT_REF", "O frame foi removido.")
            locator = frame.locator(target["locator"]["selector"])
            from playwright.async_api import Error
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError

            try:
                if await locator.count() != 1:
                    raise ServiceError("STALE_ELEMENT_REF", "Identidade do nó não é mais única.")
                current = await locator.evaluate(
                    """node => ({
                        tag: node.tagName.toLowerCase(),
                        type: node.type || '',
                        name: node.getAttribute('aria-label') || node.innerText || node.value || ''
                    })"""
                )
                if current.get("tag") != target.get("tag") or current.get(
                    "type", ""
                ) != target.get("type", ""):
                    raise ServiceError(
                        "STALE_ELEMENT_REF",
                        "O elemento mudou ou foi substituído; capture novo snapshot.",
                    )
                await HudManager.update(page, status="acting", message=f"Executando {action}...")
                if action == "click":
                    await locator.click(timeout=timeout_ms)
                elif action == "fill":
                    try:
                        await locator.focus(timeout=min(2000, timeout_ms))
                        if hasattr(locator, "press_sequentially"):
                            await locator.fill("")
                            await locator.press_sequentially(value or "", delay=30, timeout=timeout_ms)
                        else:
                            await locator.fill(value or "", timeout=timeout_ms)
                    except Exception:
                        await locator.fill(value or "", timeout=timeout_ms)
                elif action == "hover":
                    await locator.hover(timeout=timeout_ms)
                elif action == "press":
                    await locator.press(value or "", timeout=timeout_ms)
                else:
                    await locator.select_option(value=value or "", timeout=timeout_ms)
            except PlaywrightTimeoutError as exc:
                raise ServiceError(
                    "TARGET_NOT_ACTIONABLE",
                    "A ação excedeu o prazo; verifique a página antes de repetir.",
                ) from exc
            except Error as exc:
                code = "PAGE_CLOSED" if page.is_closed() else "TARGET_NOT_ACTIONABLE"
                raise ServiceError(
                    code, "Não foi possível executar a ação; observe o estado atual."
                ) from exc
            await asyncio.sleep(0)
            result: Dict[str, Any] = {
                "status": "executed",
                "action": action,
                "page_id": key,
                "url_after": redact_url(page.url),
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            }
            if page.is_closed():
                result["verification"] = {"status": "page_closed"}
                return result
            if verify == "none":
                result["verification"] = {"status": "skipped"}
                return result
            try:
                result["url_after"] = redact_url(page.url)
                attached = False if page.is_closed() else await locator.count() == 1
                result["verification"] = {
                    "status": "observed",
                    "mode": "target",
                    "target_attached": attached,
                    "url_changed": result["url_after"] != url_before,
                }
                if verify == "snapshot":
                    result["verification"]["snapshot"] = await self.observations.capture(
                        key, page, 200, include_ax=False, fast=True
                    )
            except Exception:
                result["verification"] = {
                    "status": "unavailable",
                    "code": "NAVIGATION_INTERRUPTED",
                }
            return result
