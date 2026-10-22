"""Primitivas de alto nível para reduzir round-trips de agentes."""

import asyncio
import hashlib
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from .action_resolver import ActionResolver
from .errors import ServiceError
from .named_sessions import achilles_data_dir
from .observation_engine import ObservationEngine
from .redaction import redact_url
from .session_manager import BrowserSessionManager


class AgentActions:
    def __init__(
        self,
        session: BrowserSessionManager,
        observations: ObservationEngine,
        actions: ActionResolver,
    ) -> None:
        self.session = session
        self.observations = observations
        self.actions = actions
        self.artifacts = achilles_data_dir() / "artifacts"
        self.artifacts.mkdir(parents=True, exist_ok=True)

    async def find_and_act(
        self,
        query: str,
        action: str,
        value: Optional[str] = None,
        page_id: Optional[str] = None,
        role: Optional[str] = None,
        timeout_ms: int = 5000,
    ) -> Dict[str, Any]:
        recovered = False
        for attempt in range(2):
            found = await self.observations.find(query, page_id, 10, role)
            matches = found["matches"]
            if not matches:
                raise ServiceError(
                    "ELEMENT_NOT_FOUND",
                    f"Nenhum elemento corresponde a '{query}'.",
                    retryable=True,
                    recovery={
                        "suggested_tool": "browser_find",
                        "arguments": {"query": query, "role": role} if role else {"query": query},
                    },
                )
            exact = [item for item in matches if item.get("name", "").casefold() == query.casefold()]
            target = (exact or matches)[0]
            try:
                result = await self.actions.execute(
                    action,
                    found["snapshot_id"],
                    target["element_ref"],
                    found["page_id"],
                    value,
                    timeout_ms,
                )
                return {
                    **result,
                    "matched": {key: target.get(key) for key in ("element_ref", "role", "name")},
                    "recovered": recovered,
                    "attempts": attempt + 1,
                }
            except ServiceError as exc:
                if exc.code != "STALE_ELEMENT_REF" or attempt:
                    raise
                recovered = True
        raise ServiceError("ELEMENT_NOT_FOUND", "Elemento não pôde ser recuperado.")

    async def fill_form(
        self,
        fields: Dict[str, str],
        page_id: Optional[str] = None,
        submit_query: Optional[str] = None,
    ) -> Dict[str, Any]:
        completed = []
        for label, value in fields.items():
            result = await self.find_and_act(label, "fill", value, page_id, None)
            page_id = result["page_id"]
            completed.append({"field": label, "status": "filled", "recovered": result["recovered"]})
        submitted = False
        if submit_query:
            await self.find_and_act(submit_query, "click", page_id=page_id, role="button")
            submitted = True
        return {"page_id": page_id, "fields": completed, "submitted": submitted}

    async def extract_paginated(
        self,
        items_selector: str,
        fields: Dict[str, Dict[str, Optional[str]]],
        page_id: Optional[str] = None,
        next_query: Optional[str] = None,
        max_pages: int = 10,
        max_items: int = 1000,
        dedupe_by: Optional[list[str]] = None,
        scroll: bool = False,
        limit: int = 100,
    ) -> Dict[str, Any]:
        items = []
        seen = set()
        pages = 0
        while pages < max_pages and len(items) < max_items:
            result = await self.observations.extract(
                items_selector,
                fields,
                page_id,
                min(limit, max_items - len(items)),
            )
            page_id = result["page_id"]
            added = 0
            for row in result["items"]:
                keys = dedupe_by or sorted(row)
                identity = tuple(str(row.get(key)) for key in keys)
                if identity in seen:
                    continue
                seen.add(identity)
                items.append(row)
                added += 1
                if len(items) >= max_items:
                    break
            pages += 1
            if len(items) >= max_items:
                break
            if next_query:
                try:
                    await self.find_and_act(next_query, "click", page_id=page_id)
                except ServiceError as exc:
                    if exc.code == "ELEMENT_NOT_FOUND":
                        break
                    raise
                await asyncio.sleep(0.5)
            elif scroll:
                _, page = await self.session.page(page_id)
                previous_height = await page.evaluate("document.documentElement.scrollHeight")
                await self.session.scroll(page_id=page_id, direction="bottom", amount=1000)
                await asyncio.sleep(0.5)
                current_height = await page.evaluate("document.documentElement.scrollHeight")
                if current_height <= previous_height or added == 0:
                    break
            else:
                break
        return {
            "page_id": page_id,
            "items": items,
            "count": len(items),
            "pages": pages,
            "truncated": len(items) >= max_items or pages >= max_pages,
        }

    async def wait_for_state(
        self,
        page_id: Optional[str] = None,
        text: Optional[str] = None,
        url_contains: Optional[str] = None,
        timeout_ms: int = 15000,
    ) -> Dict[str, Any]:
        if not text and not url_contains:
            raise ServiceError("INVALID_ARGUMENT", "Informe text ou url_contains.")
        key, page = await self.session.page(page_id)
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            text_ok = not text or await page.get_by_text(text, exact=False).count() > 0
            url_ok = not url_contains or url_contains in page.url
            if text_ok and url_ok:
                return {"status": "matched", "page_id": key, "url": redact_url(page.url)}
            await asyncio.sleep(0.2)
        raise ServiceError("WAIT_TIMEOUT", "O estado esperado não apareceu no prazo.", retryable=True)

    async def screenshot(
        self,
        page_id: Optional[str] = None,
        full_page: bool = False,
        image_format: str = "png",
    ) -> Dict[str, Any]:
        key, page = await self.session.page(page_id)
        suffix = "jpg" if image_format == "jpeg" else "png"
        path = self.artifacts / f"screenshot-{uuid.uuid4().hex}.{suffix}"
        payload = await page.screenshot(
            path=str(path),
            full_page=full_page,
            type=image_format,
        )
        return {
            "page_id": key,
            "path": str(path),
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "format": image_format,
        }

    async def handle_dialog(
        self,
        action: str,
        page_id: Optional[str] = None,
        prompt_text: Optional[str] = None,
        timeout_ms: int = 15000,
    ) -> Dict[str, Any]:
        key, page = await self.session.page(page_id)
        loop = asyncio.get_running_loop()
        completed = loop.create_future()

        async def resolve(dialog: Any) -> None:
            metadata = {"type": dialog.type, "message": dialog.message}
            if action == "accept":
                await dialog.accept(prompt_text)
            else:
                await dialog.dismiss()
            if not completed.done():
                completed.set_result(metadata)

        page.once("dialog", resolve)
        try:
            metadata = await asyncio.wait_for(completed, timeout_ms / 1000)
        except asyncio.TimeoutError as exc:
            page.remove_listener("dialog", resolve)
            raise ServiceError("WAIT_TIMEOUT", "Nenhum diálogo apareceu no prazo.", True) from exc
        return {"status": action + "ed", "page_id": key, "dialog": metadata}

    async def upload(
        self,
        file_path: str,
        query: str,
        page_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        source = Path(file_path).expanduser().resolve()
        if not source.is_file():
            raise ServiceError("FILE_NOT_FOUND", "Arquivo de upload não encontrado.")
        if source.stat().st_size > 50 * 1024 * 1024:
            raise ServiceError("FILE_TOO_LARGE", "Uploads são limitados a 50 MiB.")
        found = await self.observations.find(query, page_id, 10)
        if not found["matches"]:
            raise ServiceError("ELEMENT_NOT_FOUND", "Campo de upload não encontrado.")
        target = found["matches"][0]
        key, _ = await self.session.page(found["page_id"])
        metadata = self.observations.target(found["snapshot_id"], target["element_ref"], key)
        frame = self.session.registry.frames.get(metadata["frame_id"])
        if frame is None:
            raise ServiceError("STALE_ELEMENT_REF", "Frame do upload foi removido.")
        await frame.locator(metadata["locator"]["selector"]).set_input_files(str(source))
        return {
            "status": "uploaded",
            "page_id": key,
            "filename": source.name,
            "bytes": source.stat().st_size,
        }

    async def download(
        self,
        query: str,
        page_id: Optional[str] = None,
        timeout_ms: int = 30000,
    ) -> Dict[str, Any]:
        found = await self.observations.find(query, page_id, 10)
        if not found["matches"]:
            raise ServiceError("ELEMENT_NOT_FOUND", "Ação de download não encontrada.")
        target = found["matches"][0]
        key, page = await self.session.page(found["page_id"])
        metadata = self.observations.target(found["snapshot_id"], target["element_ref"], key)
        frame = self.session.registry.frames.get(metadata["frame_id"])
        if frame is None:
            raise ServiceError("STALE_ELEMENT_REF", "Frame do download foi removido.")
        async with page.expect_download(timeout=timeout_ms) as pending:
            await frame.locator(metadata["locator"]["selector"]).click(timeout=timeout_ms)
        download = await pending.value
        safe_name = Path(download.suggested_filename).name
        destination = self.artifacts / f"download-{uuid.uuid4().hex}-{safe_name}"
        await download.save_as(str(destination))
        payload = destination.read_bytes()
        return {
            "status": "downloaded",
            "page_id": key,
            "path": str(destination),
            "filename": safe_name,
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
