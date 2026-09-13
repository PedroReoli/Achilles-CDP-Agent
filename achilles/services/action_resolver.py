"""Ações com Locators nativos e resultado Observe → Act → Verify."""

import asyncio
from typing import Any, Dict, Optional

from .errors import ServiceError
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
    ) -> Dict[str, Any]:
        if action not in ("click", "fill", "hover", "press", "select"):
            raise ServiceError("INVALID_ARGUMENT", "Ação inválida.")
        if action in ("fill", "press", "select") and value is None:
            raise ServiceError("INVALID_ARGUMENT", "A ação exige value.")
        key, page = await self.session.page(page_id)
        async with self.session.registry.locks[key]:
            target = self.observations.target(snapshot_id, element_ref, key)
            before = await self.observations.capture(key, page, 1000)
            current = next((e for e in before["elements"] if e["element_ref"] == element_ref), None)
            if current is None or any(
                current[k] != target[k] for k in ("role", "name", "tag", "type")
            ):
                raise ServiceError(
                    "STALE_ELEMENT_REF",
                    "O elemento mudou ou foi substituído; capture novo snapshot.",
                )
            frame = self.session.registry.frames.get(target["frame_id"])
            if frame is None or frame.is_detached():
                raise ServiceError("STALE_ELEMENT_REF", "O frame foi removido.")
            locator = frame.locator(target["locator"]["selector"])
            from playwright.async_api import Error
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError

            try:
                if await locator.count() != 1:
                    raise ServiceError("STALE_ELEMENT_REF", "Identidade do nó não é mais única.")
                if action == "click":
                    await locator.click(timeout=timeout_ms)
                elif action == "fill":
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
            }
            if page.is_closed():
                result["verification"] = {"status": "page_closed"}
                return result
            try:
                after = await self.observations.capture(key, page, 1000)
                result["url_after"] = after["url"]
                old_refs = {e["element_ref"] for e in before["elements"]}
                new_refs = {e["element_ref"] for e in after["elements"]}
                result["verification"] = {
                    "status": "observed",
                    "dom_revision_before": before["dom_revision"],
                    "dom_revision_after": after["dom_revision"],
                    "added": sorted(new_refs - old_refs),
                    "removed": sorted(old_refs - new_refs),
                    "snapshot": after,
                }
            except Exception:
                result["verification"] = {"status": "unavailable", "code": "NAVIGATION_INTERRUPTED"}
            return result
