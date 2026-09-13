# Código completo — Achilles Application Services

Entrega da refatoração solicitada: cada arquivo completo aparece em um bloco separado. Este documento é um snapshot da entrega; os arquivos .py do repositório são a fonte de verdade. Instalação, contratos, migração e limites: [Application Services](application-services.md).

## achilles/services/session_manager.py

```python
"""Conexão CDP em modo attach e registro de targets por sessão."""

import asyncio
import inspect
import logging
import random
import uuid
from collections import deque
from typing import TYPE_CHECKING, Any, Callable, Deque, Dict, List, Optional, Set, Tuple

from .errors import ServiceError
from .redaction import redact, redact_url
from .traffic_journal import TrafficJournal

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Frame, Page, Playwright

LOG = logging.getLogger(__name__)


class TargetRegistry:
    def __init__(self) -> None:
        self.pages: Dict[str, "Page"] = {}
        self.frames: Dict[str, "Frame"] = {}
        self.active_page_id: Optional[str] = None
        self.locks: Dict[str, asyncio.Lock] = {}

    def add(self, page: "Page") -> str:
        for key, existing in self.pages.items():
            if existing is page:
                return key
        key = "page_" + uuid.uuid4().hex[:12]
        self.pages[key] = page
        self.locks[key] = asyncio.Lock()
        self.active_page_id = key
        for frame in page.frames:
            self.frame_id(frame)
        return key

    def frame_id(self, frame: "Frame") -> str:
        for key, existing in self.frames.items():
            if existing is frame:
                return key
        key = "frame_" + uuid.uuid4().hex[:12]
        self.frames[key] = frame
        return key

    def remove_frame(self, frame: "Frame") -> None:
        for key in [k for k, f in self.frames.items() if f is frame]:
            self.frames.pop(key)

    def remove(self, page: "Page") -> None:
        for key in [k for k, p in self.pages.items() if p is page]:
            self.pages.pop(key)
            self.locks.pop(key, None)
            if self.active_page_id == key:
                self.active_page_id = next(iter(self.pages), None)
        for frame in list(self.frames.values()):
            if frame.page is page:
                self.remove_frame(frame)

    def resolve(self, page_id: Optional[str] = None) -> Tuple[str, "Page"]:
        key = page_id or self.active_page_id
        page = self.pages.get(key or "")
        if key is None or page is None or page.is_closed():
            raise ServiceError("PAGE_CLOSED", "Aba indisponível; liste as abas novamente.")
        return key, page


class BrowserSessionManager:
    def __init__(
        self,
        cdp_port: int = 9222,
        journal: Optional[TrafficJournal] = None,
        connect_timeout_ms: int = 5000,
        attempts: int = 3,
    ) -> None:
        if not 1 <= cdp_port <= 65535 or attempts < 1:
            raise ValueError("Porta ou número de tentativas inválido")
        self.cdp_url = f"http://127.0.0.1:{cdp_port}"
        self.journal = journal if journal is not None else TrafficJournal()
        self.registry = TargetRegistry()
        self.connect_timeout_ms = connect_timeout_ms
        self.attempts = attempts
        self._lock: Optional[asyncio.Lock] = None
        self._playwright: Optional["Playwright"] = None
        self._browser: Optional["Browser"] = None
        self._listeners: List[Tuple[Any, str, Callable[..., Any]]] = []
        self._contexts: Set[int] = set()
        self._pages: Set[int] = set()
        self._tasks: Set[asyncio.Task[Any]] = set()
        self.console_events: Deque[Dict[str, Any]] = deque(maxlen=100)
        self.generation = 0

    def _connection_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def _listen(self, emitter: Any, event: str, callback: Callable[..., Any]) -> None:
        emitter.on(event, callback)
        self._listeners.append((emitter, event, callback))

    def _spawn(self, factory: Callable[[], Any]) -> None:
        if len(self._tasks) >= 128:
            self.journal.dropped_events += 1
            return
        task = asyncio.create_task(factory())
        self._tasks.add(task)
        task.add_done_callback(self._task_done)

    def _task_done(self, task: asyncio.Task[Any]) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            LOG.warning("Falha ao processar evento CDP: %s", type(task.exception()).__name__)

    def _page_id(self, request: Any) -> Optional[str]:
        try:
            return self._track_page(request.frame.page)
        except Exception:
            return None  # Requests de Service Workers não possuem frame.

    def _track_page(self, page: "Page") -> str:
        page_id = self.registry.add(page)
        if id(page) not in self._pages:
            self._pages.add(id(page))
            self._listen(page, "close", lambda: self._remove_page(page))
            self._listen(page, "frameattached", self.registry.frame_id)
            self._listen(page, "framedetached", self.registry.remove_frame)
            self._listen(page, "framenavigated", self.registry.frame_id)
        return page_id

    def _remove_page(self, page: "Page") -> None:
        self.registry.remove(page)
        self._pages.discard(id(page))
        remaining = []
        for emitter, event, callback in self._listeners:
            if emitter is page:
                emitter.remove_listener(event, callback)
            else:
                remaining.append((emitter, event, callback))
        self._listeners = remaining

    def _track_context(self, context: "BrowserContext") -> None:
        if id(context) in self._contexts:
            for page in context.pages:
                self._track_page(page)
            return
        self._contexts.add(id(context))
        self._listen(context, "page", self._track_page)
        self._listen(context, "request", lambda req: self.journal.request(req, self._page_id(req)))
        self._listen(
            context, "response", lambda res: self._spawn(lambda: self.journal.response(res))
        )
        self._listen(
            context, "requestfinished", lambda req: self._spawn(lambda: self.journal.finished(req))
        )
        self._listen(context, "requestfailed", self.journal.failed)
        self._listen(
            context,
            "console",
            lambda msg: self.console_events.append(
                {"type": msg.type, "text": redact(msg.text[:2000])}
            ),
        )
        for page in context.pages:
            self._track_page(page)

    async def _cleanup(self) -> None:
        for emitter, event, callback in self._listeners:
            emitter.remove_listener(event, callback)
        self._listeners.clear()
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        # Apenas encerra o transporte Playwright; não chama Browser.close nem Context.close.
        if self._playwright is not None:
            await self._playwright.stop()
        self._playwright = None
        self._browser = None
        self._contexts.clear()
        self._pages.clear()
        self.registry = TargetRegistry()

    async def connect(self) -> None:
        async with self._connection_lock():
            if self._browser is not None and self._browser.is_connected():
                for context in self._browser.contexts:
                    self._track_context(context)
                return
            await self._cleanup()
            from playwright.async_api import async_playwright

            for attempt in range(self.attempts):
                try:
                    self._playwright = await async_playwright().start()
                    connect = self._playwright.chromium.connect_over_cdp
                    options: Dict[str, Any] = {"timeout": self.connect_timeout_ms}
                    if "no_defaults" in inspect.signature(connect).parameters:
                        options["no_defaults"] = True
                    self._browser = await connect(self.cdp_url, **options)
                    self._listen(
                        self._browser,
                        "disconnected",
                        lambda: LOG.info("Chrome desconectado; reconexão na próxima operação"),
                    )
                    self.generation += 1
                    for context in self._browser.contexts:
                        self._track_context(context)
                    return
                except Exception as exc:
                    await self._cleanup()
                    if attempt + 1 == self.attempts:
                        raise ServiceError(
                            "CDP_UNAVAILABLE", "Chrome CDP indisponível na porta configurada.", True
                        ) from exc
                    await asyncio.sleep(min(0.25 * 2**attempt, 2) + random.uniform(0, 0.1))

    async def page(self, page_id: Optional[str] = None) -> Tuple[str, "Page"]:
        await self.connect()
        return self.registry.resolve(page_id)

    async def list_pages(self) -> Dict[str, Any]:
        await self.connect()
        pages: List[Dict[str, Any]] = []
        for key, page in list(self.registry.pages.items()):
            if page.is_closed():
                continue
            try:
                title = await page.title()
            except Exception:
                title = ""
            pages.append(
                {
                    "page_id": key,
                    "url": redact_url(page.url),
                    "title": redact(title),
                    "selected": key == self.registry.active_page_id,
                    "frames": [
                        {
                            "frame_id": self.registry.frame_id(f),
                            "url": redact_url(f.url),
                            "parent_frame_id": self.registry.frame_id(f.parent_frame)
                            if f.parent_frame
                            else None,
                        }
                        for f in page.frames
                    ],
                }
            )
        return {
            "pages": pages,
            "generation": self.generation,
            "selection_policy": "explicit_or_latest_discovered",
        }

    async def select_page(self, page_id: str) -> Dict[str, Any]:
        key, page = await self.page(page_id)
        await page.bring_to_front()
        self.registry.active_page_id = key
        return {"page_id": key, "url": redact_url(page.url)}

    async def drain(self) -> None:
        tasks = list(self._tasks)
        if tasks:
            await asyncio.wait(tasks, timeout=6)

    async def close(self) -> None:
        async with self._connection_lock():
            await self._cleanup()
```

## achilles/services/traffic_journal.py

```python
"""Registro HTTP correlacionado e limitado; exports sempre redigidos."""

import asyncio
import copy
import shlex
import time
import uuid
from collections import deque
from typing import TYPE_CHECKING, Any, Deque, Dict, List, Optional
from urllib.parse import parse_qsl, urlsplit

from .redaction import redact, redact_body, redact_url

if TYPE_CHECKING:
    from playwright.async_api import Request, Response


class TrafficJournal:
    def __init__(self, max_records: int = 500, max_body_bytes: int = 65536) -> None:
        if max_records < 1 or max_body_bytes < 1:
            raise ValueError("Limites devem ser positivos")
        self.records: Deque[Dict[str, Any]] = deque(maxlen=max_records)
        self.max_body_bytes = max_body_bytes
        self._index: Dict["Request", Dict[str, Any]] = {}
        self._body_slots: Optional[asyncio.Semaphore] = None
        self.dropped_events = 0

    def request(self, request: "Request", page_id: Optional[str]) -> None:
        if len(self.records) == self.records.maxlen:
            old = self.records[0]
            self._index.pop(old["_key"], None)
        try:
            body = request.post_data or ""
        except Exception:
            body = ""
        encoded_body = body.encode("utf-8")
        redirected = request.redirected_from if hasattr(request, "redirected_from") else None
        predecessor = self._index.get(redirected) if redirected is not None else None
        record: Dict[str, Any] = {
            "_key": request,
            "request_id": uuid.uuid4().hex,
            "page_id": page_id,
            "method": request.method,
            "url": request.url,
            "resource_type": request.resource_type,
            "started_at": time.time(),
            "request_headers": dict(request.headers),
            "request_body": encoded_body[: self.max_body_bytes].decode("utf-8", errors="replace"),
            "request_body_truncated": len(encoded_body) > self.max_body_bytes,
            "redirected_from": predecessor["request_id"] if predecessor else None,
            "status": None,
            "response_headers": {},
            "response_body": None,
            "body_state": "pending",
            "timings": {},
            "failure": None,
        }
        self.records.append(record)
        self._index[request] = record

    async def response(self, response: "Response") -> None:
        record = self._index.get(response.request)
        if record is None:
            return
        record["status"] = response.status
        record["response_headers"] = dict(response.headers)
        try:
            record["response_headers"] = await response.all_headers()
            record["request_headers"] = await response.request.all_headers()
        except Exception:
            record["headers_incomplete"] = True

    async def finished(self, request: "Request") -> None:
        record = self._index.get(request)
        if record is None:
            return
        record["timings"] = dict(request.timing)
        try:
            if self._body_slots is None:
                self._body_slots = asyncio.Semaphore(4)
            async with self._body_slots:
                response = await request.response()
                if response is None:
                    record["body_state"] = "unavailable"
                    return
                await self.response(response)
                headers = record["response_headers"]
                mime = headers.get("content-type", "").lower()
                length = headers.get("content-length", "")
                if "text/event-stream" in mime:
                    record["body_state"] = "streaming_not_captured"
                    return
                if not any(t in mime for t in ("json", "text/", "javascript", "xml")):
                    record["body_state"] = "binary_omitted"
                    return
                # Não materializa corpos sem tamanho conhecido ou comprimidos arbitrariamente.
                if (
                    not length.isdigit()
                    or int(length) > self.max_body_bytes
                    or headers.get("content-encoding")
                ):
                    record["body_state"] = "size_or_encoding_omitted"
                    return
                body = await asyncio.wait_for(response.body(), timeout=5)
                record["response_body"] = body[: self.max_body_bytes].decode(
                    "utf-8", errors="replace"
                )
                record["body_state"] = (
                    "truncated" if len(body) > self.max_body_bytes else "captured"
                )
        except Exception:
            record["body_state"] = "unavailable"

    def failed(self, request: "Request") -> None:
        record = self._index.get(request)
        if record is not None:
            record["failure"] = "NETWORK_REQUEST_FAILED"
            record["timings"] = dict(request.timing)
            record["body_state"] = "failed"

    def query(self, limit: int = 50, page_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if not 1 <= limit <= 500:
            raise ValueError("limit deve estar entre 1 e 500")
        rows = [r for r in self.records if page_id is None or r["page_id"] == page_id]
        return [self.public_record(r) for r in rows[-limit:]]

    def clear(self) -> None:
        self.records.clear()
        self._index.clear()

    @staticmethod
    def public_record(record: Dict[str, Any]) -> Dict[str, Any]:
        result = copy.deepcopy({k: v for k, v in record.items() if not k.startswith("_")})
        result["url"] = redact_url(result["url"])
        for side in ("request", "response"):
            headers = result.get(side + "_headers", {})
            body = result.get(side + "_body")
            if body is not None:
                result[side + "_body"] = redact_body(body, headers.get("content-type", ""))
            result[side + "_headers"] = redact(headers)
        return result

    def navigation(self, page_id: str, url: str) -> Optional[Dict[str, Any]]:
        return next(
            (
                r
                for r in reversed(self.records)
                if r["page_id"] == page_id
                and r["resource_type"] == "document"
                and r["url"].split("#")[0] == url.split("#")[0]
                and r["status"] is not None
            ),
            None,
        )

    @staticmethod
    def to_curl(record: Dict[str, Any], shell: str = "posix") -> str:
        if shell not in ("posix", "powershell"):
            raise ValueError("Shell inválido")
        r = TrafficJournal.public_record(record)
        args = [
            "curl" if shell == "posix" else "curl.exe",
            "--request",
            r["method"],
            "--url",
            r["url"],
        ]
        for key, value in r["request_headers"].items():
            if not key.startswith(":") and key.lower() not in ("content-length", "host"):
                args.extend(["--header", f"{key}: {value}"])
        if r.get("request_body"):
            args.extend(["--data-raw", r["request_body"]])
        if shell == "posix":
            return " ".join(shlex.quote(a) for a in args)
        return "& " + " ".join("'" + a.replace("'", "''") + "'" for a in args)

    def postman(self) -> Dict[str, Any]:
        items: List[Dict[str, Any]] = []
        for raw in self.records:
            r = self.public_record(raw)
            p = urlsplit(r["url"])
            url: Dict[str, Any] = {
                "raw": r["url"],
                "protocol": p.scheme,
                "host": (p.hostname or "").split("."),
                "path": p.path.strip("/").split("/") if p.path.strip("/") else [],
                "query": [
                    {"key": k, "value": v} for k, v in parse_qsl(p.query, keep_blank_values=True)
                ],
            }
            if p.port:
                url["port"] = str(p.port)
            request: Dict[str, Any] = {
                "method": r["method"],
                "url": url,
                "header": [
                    {"key": k, "value": str(v)}
                    for k, v in r["request_headers"].items()
                    if not k.startswith(":")
                ],
            }
            if r.get("request_body"):
                request["body"] = {"mode": "raw", "raw": r["request_body"]}
            items.append({"name": f"{r['method']} {p.path}", "request": request})
        return {
            "info": {
                "name": "Achilles — redacted",
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            },
            "item": items,
        }
```

## achilles/services/observation_engine.py

```python
"""Snapshots limitados, identidade por nó e observação de frames/shadow roots."""

import asyncio
import json
import uuid
from collections import OrderedDict
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .errors import ServiceError
from .redaction import redact, redact_url
from .session_manager import BrowserSessionManager

if TYPE_CHECKING:
    from playwright.async_api import Page


EXTRACT = r"""({key, attribute, limit}) => {
    let state = window[key];
    if (!state) {
        state = {epoch: crypto.randomUUID ? crypto.randomUUID() : String(Math.random()), revision: 0,
                 nodes: new WeakMap(), counter: 0, roots: new WeakSet()};
        Object.defineProperty(window, key, {value: state, configurable: true});
        state.observer = new MutationObserver(records => {
            if (records.some(r => !(r.type === 'attributes' && r.attributeName === attribute))) state.revision++;
        });
    }
    const implicit = el => {
        const tag = el.localName;
        const type = (el.getAttribute('type') || 'text').toLowerCase();
        if (tag === 'button') return 'button';
        if (tag === 'a' && el.hasAttribute('href')) return 'link';
        if (tag === 'textarea' || el.isContentEditable) return 'textbox';
        if (tag === 'select') return el.multiple ? 'listbox' : 'combobox';
        if (tag === 'input') return ({checkbox:'checkbox',radio:'radio',range:'slider',number:'spinbutton',
            button:'button',submit:'button',reset:'button',search:'searchbox'})[type] || 'textbox';
        return el.hasAttribute('tabindex') ? 'generic' : '';
    };
    const nameOf = el => {
        const root = el.getRootNode();
        const ids = (el.getAttribute('aria-labelledby') || '').split(/\s+/).filter(Boolean);
        const labelled = ids.map(id => root.getElementById?.(id)?.textContent || '').join(' ').trim();
        if (labelled) return labelled;
        if (el.hasAttribute('aria-label')) return el.getAttribute('aria-label');
        if (el.labels?.length) return Array.from(el.labels).map(x => x.textContent).join(' ');
        if (['button','submit','reset'].includes(el.type)) return el.value || el.textContent || '';
        return el.getAttribute('alt') || el.textContent || el.getAttribute('title') || el.getAttribute('placeholder') || '';
    };
    const result = [];
    let visited = 0, truncated = false;
    const walk = root => {
        if (!state.roots.has(root)) {
            state.observer.observe(root, {subtree:true, childList:true, attributes:true, characterData:true});
            state.roots.add(root);
        }
        for (const el of root.querySelectorAll('*')) {
            if (++visited > 20000 || result.length >= limit) { truncated = true; return; }
            if (el.shadowRoot) walk(el.shadowRoot);
            const role = el.getAttribute('role')?.split(' ')[0] || implicit(el);
            if (!role || ['none','presentation'].includes(role) || el.type === 'hidden') continue;
            const rect = el.getBoundingClientRect(), style = getComputedStyle(el);
            if (!rect.width || !rect.height || style.display === 'none' || style.visibility === 'hidden'
                || el.closest('[aria-hidden="true"], [inert]')) continue;
            let ref = state.nodes.get(el);
            if (!ref) { ref = state.epoch + '_' + (++state.counter); state.nodes.set(el, ref); el.setAttribute(attribute, ref); }
            const name = nameOf(el).replace(/\s+/g,' ').trim().slice(0,200);
            result.push({node_ref:ref, role, name, tag:el.localName, type:el.type || '',
                disabled:el.matches(':disabled') || el.getAttribute('aria-disabled') === 'true',
                checked:el.hasAttribute('aria-checked') ? el.getAttribute('aria-checked') : (typeof el.checked === 'boolean' ? el.checked : null),
                expanded:el.getAttribute('aria-expanded'), selected:el.getAttribute('aria-selected'),
                in_viewport:rect.bottom > 0 && rect.right > 0 && rect.top < innerHeight && rect.left < innerWidth});
        }
    };
    walk(document);
    return {epoch:state.epoch, revision:state.revision, elements:result, truncated};
}"""


class ObservationEngine:
    def __init__(self, session: BrowserSessionManager, max_snapshots: int = 32) -> None:
        self.session = session
        self.max_snapshots = max_snapshots
        self.snapshots: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        nonce = uuid.uuid4().hex
        self.state_key = "__achilles_" + nonce
        self.attribute = "data-achilles-" + nonce
        self._revision = 0
        self._signatures: Dict[str, str] = {}

    async def _accessibility(self, page: "Page", elements: Any) -> str:
        client = None
        mapped = 0
        targets = {e["element_ref"].split("/", 1)[1]: e for e in elements}
        try:
            client = await page.context.new_cdp_session(page)
            dom = await asyncio.wait_for(
                client.send("DOMSnapshot.captureSnapshot", {"computedStyles": []}), 5
            )
            strings = dom["strings"]
            for document in dom["documents"]:
                nodes = document["nodes"]
                backend_targets = {}
                for index, attributes in enumerate(nodes.get("attributes", [])):
                    for offset in range(0, len(attributes), 2):
                        if strings[attributes[offset]] == self.attribute:
                            target = targets.get(strings[attributes[offset + 1]])
                            if target is not None:
                                backend_targets[nodes["backendNodeId"][index]] = target
                if not backend_targets:
                    continue
                try:
                    ax = await asyncio.wait_for(
                        client.send(
                            "Accessibility.getFullAXTree", {"frameId": strings[document["frameId"]]}
                        ),
                        5,
                    )
                except Exception:
                    continue  # OOPIF indisponível é declarado como fallback parcial.
                for node in ax["nodes"]:
                    target = backend_targets.get(node.get("backendDOMNodeId"))
                    if target is None or node.get("ignored"):
                        continue
                    target["name"] = node.get("name", {}).get("value", "")[:200]
                    target["role"] = node.get("role", {}).get("value", target["role"])
                    for prop in node.get("properties", []):
                        if prop["name"] in ("checked", "disabled", "expanded", "selected"):
                            target[prop["name"]] = prop["value"].get("value")
                    target["accessible_name_source"] = "chrome_ax"
                    mapped += 1
        except Exception:
            return "dom_fallback"
        finally:
            if client is not None:
                try:
                    await client.detach()
                except Exception:
                    pass  # Transporte já desconectado; nenhum recurso remoto a liberar.
        return "chrome_ax" if mapped == len(elements) else "chrome_ax_with_dom_fallback"

    async def snapshot(self, page_id: Optional[str] = None, limit: int = 200) -> Dict[str, Any]:
        key, page = await self.session.page(page_id)
        async with self.session.registry.locks[key]:
            return await self.capture(key, page, limit)

    async def capture(self, page_id: str, page: "Page", limit: int = 200) -> Dict[str, Any]:
        if page.is_closed():
            raise ServiceError("PAGE_CLOSED", "A aba foi fechada.")
        limit = min(max(limit, 1), 1000)
        elements: List[Dict[str, Any]] = []
        frame_states: Dict[str, Any] = {}
        warnings = []
        for frame in list(page.frames)[:64]:
            frame_id = self.session.registry.frame_id(frame)
            try:
                data = await frame.evaluate(
                    EXTRACT,
                    {
                        "key": self.state_key,
                        "attribute": self.attribute,
                        "limit": max(1, limit - len(elements)),
                    },
                )
            except Exception:
                warnings.append({"frame_id": frame_id, "code": "FRAME_UNAVAILABLE"})
                continue
            frame_states[frame_id] = {"epoch": data["epoch"], "revision": data["revision"]}
            if data["truncated"]:
                warnings.append({"frame_id": frame_id, "code": "SNAPSHOT_TRUNCATED"})
            for item in data["elements"]:
                item["element_ref"] = f"{frame_id}/{item.pop('node_ref')}"
                node_ref = item["element_ref"].split("/", 1)[1]
                item["frame_id"] = frame_id
                item["locator"] = {
                    "strategy": "css",
                    "selector": f'[{self.attribute}="{node_ref}"]',
                }
                elements.append(item)
            if len(elements) >= limit:
                warnings.append({"code": "SNAPSHOT_TRUNCATED"})
                break
        accessibility = await self._accessibility(page, elements)
        signature = json.dumps([page.url, frame_states], sort_keys=True)
        if self._signatures.get(page_id) != signature:
            self._revision += 1
            self._signatures[page_id] = signature
        self._signatures = {
            k: v for k, v in self._signatures.items() if k in self.session.registry.pages
        }
        snapshot: Dict[str, Any] = {
            "snapshot_id": "snap_" + uuid.uuid4().hex,
            "page_id": page_id,
            "generation": self.session.generation,
            "dom_revision": self._revision,
            "url": redact_url(page.url),
            "elements": elements,
            "frames": frame_states,
            "warnings": warnings,
            "accessibility": accessibility,
            "unsupported": ["closed_shadow_roots", "canvas_semantics"],
        }
        self.snapshots[snapshot["snapshot_id"]] = snapshot
        while len(self.snapshots) > self.max_snapshots:
            self.snapshots.popitem(last=False)
        return self.public(snapshot)

    @staticmethod
    def public(snapshot: Dict[str, Any]) -> Dict[str, Any]:
        result = redact(snapshot)
        result["compact"] = "\n".join(
            f"[{e['element_ref']}] {e['role']} {json.dumps(e['name'], ensure_ascii=False)}"
            + (" disabled" if e["disabled"] else "")
            for e in result["elements"]
        )
        return result

    def target(self, snapshot_id: str, element_ref: str, page_id: str) -> Dict[str, Any]:
        snapshot = self.snapshots.get(snapshot_id)
        if (
            snapshot is None
            or snapshot["page_id"] != page_id
            or snapshot["generation"] != self.session.generation
        ):
            raise ServiceError(
                "STALE_ELEMENT_REF", "Snapshot expirado; capture a página novamente."
            )
        target = next((e for e in snapshot["elements"] if e["element_ref"] == element_ref), None)
        if target is None:
            raise ServiceError("STALE_ELEMENT_REF", "Referência ausente no snapshot.")
        return target

    async def close(self) -> None:
        script = """({key, attribute}) => {
            window[key]?.observer.disconnect();
            const clean = root => { for (const el of root.querySelectorAll('*')) {
                el.removeAttribute(attribute); if (el.shadowRoot) clean(el.shadowRoot);
            }};
            clean(document); delete window[key];
        }"""
        for frame in list(self.session.registry.frames.values()):
            try:
                await asyncio.wait_for(
                    frame.evaluate(script, {"key": self.state_key, "attribute": self.attribute}), 1
                )
            except Exception:
                continue  # Frame removido/desconectado não permite remoção da instrumentação.
        self.snapshots.clear()
        self._signatures.clear()
```

## achilles/services/action_resolver.py

```python
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
            # Dá oportunidade aos observers de publicar mutações; não aguarda networkidle.
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
```

## achilles/services/security_engine.py

```python
"""Auditoria passiva com evidência, cobertura explícita e confiança ponderada."""

import base64
import json
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from .redaction import SECRETS, mask, redact_url
from .session_manager import BrowserSessionManager
from .traffic_journal import TrafficJournal


class SecurityAuditEngine:
    WEIGHTS = {"critical": 35, "high": 20, "medium": 10, "low": 3}

    def __init__(self, session: BrowserSessionManager, journal: TrafficJournal) -> None:
        self.session = session
        self.journal = journal

    @staticmethod
    def inspect_jwt(token: str) -> Dict[str, Any]:
        try:
            parts = token.split(".")
            if len(parts) != 3 or len(token) > 32768:
                return {"decoded": False, "signature_verified": False, "issues": []}
            header, payload = [
                json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4))) for p in parts[:2]
            ]
            if not isinstance(header, dict) or not isinstance(payload, dict):
                raise ValueError("JWT objects required")
            issues = []
            if str(header.get("alg", "")).lower() == "none":
                issues.append("unsigned_jwt")
            if "exp" not in payload:
                issues.append("missing_expiration")
            if (
                payload.get("role") in ("service_role", "admin", "administrator")
                or payload.get("is_admin") is True
            ):
                issues.append("administrative_claim")
            return {"decoded": True, "signature_verified": False, "issues": issues}
        except (ValueError, TypeError, UnicodeError):
            return {"decoded": False, "signature_verified": False, "issues": []}

    @classmethod
    def analyze(
        cls,
        url: str,
        response_headers: Optional[Dict[str, str]],
        cookies: List[Dict[str, Any]],
        storage: Dict[str, Any],
        records: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        findings: List[Dict[str, Any]] = []
        seen = set()

        def add(
            rule: str, severity: str, confidence: float, title: str, evidence: str, remediation: str
        ) -> None:
            identity = (rule, evidence)
            if identity in seen:
                return
            seen.add(identity)
            findings.append(
                {
                    "rule_id": rule,
                    "severity": severity,
                    "confidence": confidence,
                    "title": title,
                    "evidence": evidence,
                    "remediation": remediation,
                }
            )

        if response_headers is not None:
            h = {k.lower(): v for k, v in response_headers.items()}
            if "content-security-policy" not in h:
                add(
                    "CSP_MISSING",
                    "medium",
                    0.8,
                    "CSP ausente no header da resposta capturada",
                    "Content-Security-Policy não observado; política via meta não avaliada.",
                    "Defina CSP apropriada para o documento.",
                )
            if urlsplit(url).scheme == "https" and "strict-transport-security" not in h:
                add(
                    "HSTS_MISSING",
                    "low",
                    0.9,
                    "HSTS ausente",
                    "Resposta HTTPS sem HSTS.",
                    "Configure HSTS após validar HTTPS e subdomínios.",
                )
            if (
                "x-frame-options" not in h
                and "frame-ancestors" not in h.get("content-security-policy", "").lower()
            ):
                add(
                    "FRAME_PROTECTION_MISSING",
                    "medium",
                    0.7,
                    "Proteção de enquadramento ausente",
                    "X-Frame-Options e CSP frame-ancestors não observados.",
                    "Configure CSP frame-ancestors conforme integrações permitidas.",
                )

        for r in records:
            headers = {k.lower(): v for k, v in r.get("response_headers", {}).items()}
            req_headers = {k.lower(): v for k, v in r.get("request_headers", {}).items()}
            origin = req_headers.get("origin")
            allowed = headers.get("access-control-allow-origin")
            credentials = headers.get("access-control-allow-credentials", "").lower() == "true"
            if origin and allowed == origin and credentials:
                add(
                    "CORS_REFLECTION_CANDIDATE",
                    "low",
                    0.35,
                    "Origin coincidente com credentials",
                    f"Exchange {r.get('request_id', 'unknown')}; não prova reflexão arbitrária.",
                    "Confirme allowlist no servidor; coincidência com origem autorizada é legítima.",
                )
            if allowed == "*" and credentials:
                add(
                    "CORS_INVALID_CREDENTIALS",
                    "low",
                    1.0,
                    "CORS wildcard incompatível com credentials",
                    f"Exchange {r.get('request_id', 'unknown')}",
                    "Configure origem explícita; o navegador bloqueia leitura credentialed com wildcard.",
                )

        for cookie in cookies:
            name = str(cookie.get("name", ""))
            if not any(s in name.lower() for s in ("session", "auth", "token", "jwt", "sid")):
                continue
            for flag in ("httpOnly", "secure"):
                if not cookie.get(flag) and (flag != "secure" or urlsplit(url).scheme == "https"):
                    add(
                        "COOKIE_" + flag.upper(),
                        "medium",
                        0.8,
                        f"Cookie de sessão sem {flag}",
                        mask(name),
                        f"Revise flag {flag} no cookie de sessão.",
                    )
            if cookie.get("sameSite") == "None" and not cookie.get("secure"):
                add(
                    "COOKIE_SAMESITE",
                    "medium",
                    1.0,
                    "SameSite=None sem Secure",
                    mask(name),
                    "Use Secure com SameSite=None.",
                )

        sources = [("storage", json.dumps(storage, ensure_ascii=False))]
        for record in records:
            sources.append(
                (
                    "exchange:" + str(record.get("request_id", "unknown")),
                    json.dumps(
                        {
                            k: record.get(k)
                            for k in (
                                "url",
                                "request_headers",
                                "response_headers",
                                "request_body",
                                "response_body",
                            )
                        },
                        ensure_ascii=False,
                    ),
                )
            )
        for source, text in sources:
            for match in SECRETS.finditer(text):
                token = match.group()
                evidence = f"{source}: {mask(token)}"
                if token.startswith("eyJ"):
                    jwt = cls.inspect_jwt(token)
                    for issue in jwt["issues"]:
                        severity = "high" if issue == "unsigned_jwt" else "medium"
                        add(
                            "JWT_" + issue.upper(),
                            severity,
                            0.9,
                            issue,
                            evidence,
                            "Revise emissão e validação no servidor; decodificação não comprova aceitação do token.",
                        )
                    # Token client-side administrativo não demonstra por si só falha de autorização.
                else:
                    add(
                        "CLIENT_SECRET",
                        "critical",
                        0.9,
                        "Credencial privada observada no cliente",
                        evidence,
                        "Confirme a credencial, rotacione-a e mova seu uso para o servidor.",
                    )
        score = min(100, round(sum(cls.WEIGHTS[f["severity"]] * f["confidence"] for f in findings)))
        return {
            "page_url": redact_url(url),
            "mode": "passive",
            "findings": findings,
            "summary": {
                "risk_score": score,
                "total_findings": len(findings),
                "formula": "min(100, sum(severity_weight * confidence))",
            },
            "coverage": {
                "navigation_response_headers": "observed"
                if response_headers is not None
                else "not_observed",
                "authorization_exploitation": "not_tested",
                "database_integrity": "not_tested",
            },
        }

    async def audit(self, page_id: Optional[str] = None) -> Dict[str, Any]:
        key, page = await self.session.page(page_id)
        async with self.session.registry.locks[key]:
            await self.session.drain()
            storage: Dict[str, Any] = {}
            skipped = []
            for frame in list(page.frames)[:64]:
                frame_id = self.session.registry.frame_id(frame)
                try:
                    storage[frame_id] = await frame.evaluate("""() => {
                        const read = store => { const out = {}; let bytes = 0;
                            for (let i=0; i<Math.min(store.length,200); i++) {
                                const k=store.key(i), v=store.getItem(k) || '';
                                if ((bytes += v.length) > 262144) break; out[k]=v.slice(0,32768);
                            } return out; };
                        return {local:read(localStorage),session:read(sessionStorage)};
                    }""")
                except Exception:
                    skipped.append(frame_id)
            cookies = [dict(cookie) for cookie in await page.context.cookies([page.url])]
            navigation = self.journal.navigation(key, page.url)
            records = [r for r in self.journal.records if r["page_id"] == key]
            result = self.analyze(
                page.url,
                navigation["response_headers"] if navigation else None,
                cookies,
                storage,
                records,
            )
            result["coverage"]["storage_skipped_frames"] = skipped
            result["coverage"]["storage_limits"] = {
                "keys_per_store": 200,
                "characters_per_store": 262144,
            }
            return result
```

## achilles/services/application.py

```python
"""Catálogo e contratos únicos para os transportes REST e MCP."""

import asyncio
import logging
from typing import Any, Dict, Literal, Optional, Type

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .action_resolver import ActionResolver
from .errors import ServiceError
from .observation_engine import ObservationEngine
from .security_engine import SecurityAuditEngine
from .session_manager import BrowserSessionManager
from .traffic_journal import TrafficJournal


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PageArguments(Arguments):
    page_id: Optional[str] = Field(None, min_length=1, max_length=128)


class SelectArguments(Arguments):
    page_id: str = Field(min_length=1, max_length=128)


class SnapshotArguments(PageArguments):
    limit: int = Field(200, ge=1, le=1000)


class TrafficArguments(PageArguments):
    limit: int = Field(50, ge=1, le=500)


class CurlArguments(Arguments):
    request_id: str = Field(min_length=1, max_length=128)
    shell: Literal["posix", "powershell"] = "posix"


class ActionArguments(Arguments):
    action: Literal["click", "fill", "hover", "press", "select"]
    page_id: str = Field(min_length=1, max_length=128)
    snapshot_id: str = Field(min_length=1, max_length=128)
    element_ref: str = Field(min_length=1, max_length=256)
    value: Optional[str] = Field(None, max_length=65536)
    timeout_ms: int = Field(5000, ge=100, le=30000)

    @model_validator(mode="after")
    def value_required(self) -> "ActionArguments":
        if self.action in ("fill", "press", "select") and self.value is None:
            raise ValueError("A ação exige value")
        return self


CONTRACTS: Dict[str, Type[Arguments]] = {
    "browser_status": Arguments,
    "browser_list_pages": Arguments,
    "browser_select_page": SelectArguments,
    "browser_snapshot": SnapshotArguments,
    "browser_action": ActionArguments,
    "network_query": TrafficArguments,
    "network_curl": CurlArguments,
    "network_postman": Arguments,
    "security_audit": PageArguments,
}
DESCRIPTIONS = {
    "browser_status": "Estado do transporte e da captura, sem conectar automaticamente.",
    "browser_list_pages": "Lista abas e frames disponíveis no Chrome conectado.",
    "browser_select_page": "Seleciona explicitamente uma aba e a traz para frente.",
    "browser_snapshot": "Snapshot versionado, incluindo frames e Shadow DOM aberto.",
    "browser_action": "Executa Locator e retorna observação posterior; não repete a ação automaticamente.",
    "network_query": "Últimos exchanges HTTP redigidos com status e response headers.",
    "network_curl": "Exporta um exchange redigido para POSIX ou PowerShell.",
    "network_postman": "Coleção Postman 2.1 com credenciais redigidas.",
    "security_audit": "Auditoria passiva com evidência e cobertura ausente explícitas.",
}


class ApplicationServices:
    def __init__(self, cdp_port: int = 9222) -> None:
        self.journal = TrafficJournal()
        self.session = BrowserSessionManager(cdp_port, self.journal)
        self.observations = ObservationEngine(self.session)
        self.actions = ActionResolver(self.session, self.observations)
        self.security = SecurityAuditEngine(self.session, self.journal)
        self.closed = False

    @staticmethod
    def tools() -> Dict[str, Any]:
        return {
            "tools": [
                {
                    "name": name,
                    "description": DESCRIPTIONS[name],
                    "inputSchema": contract.model_json_schema(),
                    "outputSchema": {"type": "object", "additionalProperties": True},
                    "annotations": {
                        "readOnlyHint": name not in ("browser_action", "browser_select_page"),
                        "destructiveHint": name == "browser_action",
                        "idempotentHint": name != "browser_action",
                        "openWorldHint": True,
                    },
                }
                for name, contract in CONTRACTS.items()
            ]
        }

    async def call(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return await asyncio.wait_for(self._invoke(name, arguments), timeout=90)
        except asyncio.TimeoutError as exc:
            raise ServiceError(
                "OPERATION_TIMEOUT", "Operação excedeu o prazo; observe o estado antes de repetir."
            ) from exc
        except ServiceError:
            raise
        except Exception as exc:
            logging.getLogger(__name__).error("Falha em %s: %s", name, type(exc).__name__)
            raise ServiceError(
                "INTERNAL_ERROR", "Falha interna; nenhum detalhe sensível foi retornado."
            ) from exc

    async def _invoke(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if name not in CONTRACTS:
            raise ServiceError("UNKNOWN_TOOL", "Ferramenta desconhecida.")
        if self.closed:
            raise ServiceError("SESSION_CLOSED", "Serviços encerrados.")
        try:
            args = CONTRACTS[name].model_validate(arguments).model_dump()
        except ValidationError as exc:
            raise ServiceError(
                "INVALID_ARGUMENT", "Argumentos não correspondem ao inputSchema."
            ) from exc
        if name == "browser_status":
            return {
                "cdp_url": self.session.cdp_url,
                "mode": "attach",
                "generation": self.session.generation,
                "recorded_requests": len(self.journal.records),
                "dropped_events": self.journal.dropped_events,
            }
        if name == "browser_list_pages":
            return await self.session.list_pages()
        if name == "browser_select_page":
            return await self.session.select_page(**args)
        if name == "browser_snapshot":
            return await self.observations.snapshot(**args)
        if name == "browser_action":
            return await self.actions.execute(**args)
        if name == "network_query":
            await self.session.connect()
            await self.session.drain()
            return {
                "records": self.journal.query(**args),
                "dropped_events": self.journal.dropped_events,
            }
        if name == "network_postman":
            return self.journal.postman()
        if name == "network_curl":
            record = next(
                (r for r in self.journal.records if r["request_id"] == args["request_id"]), None
            )
            if record is None:
                raise ServiceError("RECORD_NOT_FOUND", "Exchange expirado ou inexistente.")
            return {
                "shell": args["shell"],
                "redacted": True,
                "curl": self.journal.to_curl(record, args["shell"]),
            }
        return await self.security.audit(**args)

    async def close(self) -> None:
        await self.observations.close()
        await self.session.close()
        self.journal.clear()
        self.closed = True
```

## achilles/services/errors.py

```python
"""Erros públicos estáveis, sem detalhes sensíveis do navegador."""

from typing import Any, Dict


class ServiceError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable

    def as_dict(self) -> Dict[str, Any]:
        return {"code": self.code, "message": str(self), "retryable": self.retryable}
```

## achilles/services/redaction.py

```python
"""Redação recursiva usada antes de qualquer exportação."""

import hashlib
import json
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SENSITIVE = re.compile(
    r"authorization|cookie|token|secret|password|passwd|api[-_]?key|credential", re.I
)
ASSIGNMENT = re.compile(
    r"""(?i)((?:password|passwd|token|secret|api[_-]?key)["']?\s*[:=]\s*["']?)([^\s"'&,;}]+)"""
)
SECRETS = re.compile(
    r"(?:sbp_[A-Za-z0-9]{20,}|sb_secret_[A-Za-z0-9_-]+|[sr]k_live_[A-Za-z0-9]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*)"
)


def mask(value: str) -> str:
    prefix = value[:8] if value.startswith(("sbp_", "sb_secret_")) else "[REDACTED]"
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}... [sha256:{digest}]"


def redact(value: Any, key: str = "") -> Any:
    if SENSITIVE.search(key) and value is not None:
        return mask(str(value))
    if isinstance(value, dict):
        return {str(k): redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [redact(v) for v in value]
    if isinstance(value, str):
        if value.startswith(("https://", "http://")):
            return redact_url(value)
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            parsed = None
        if isinstance(parsed, (dict, list)):
            return json.dumps(redact(parsed), ensure_ascii=False)
        text = SECRETS.sub(lambda m: mask(m.group()), value)
        return ASSIGNMENT.sub(lambda m: m.group(1) + mask(m.group(2)), text)
    return value


def redact_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        host = parts.netloc.rsplit("@", 1)[-1]
        query = urlencode(
            [(k, redact(v, k)) for k, v in parse_qsl(parts.query, keep_blank_values=True)]
        )
        return urlunsplit((parts.scheme, host, redact(parts.path), query, redact(parts.fragment)))
    except ValueError:
        return mask(url)


def redact_body(body: str, content_type: str) -> str:
    if "x-www-form-urlencoded" in content_type:
        return urlencode([(k, redact(v, k)) for k, v in parse_qsl(body, keep_blank_values=True)])
    if "multipart/" in content_type:
        return mask(body)
    return str(redact(body))
```

## achilles/services/__init__.py

```python
"""Serviços compartilhados pelos transportes REST e MCP."""
```

## achilles/api/server.py

```python
"""REST local autenticado; toda operação delega aos Application Services."""

import hmac
import ipaddress
import os
import secrets
import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from achilles.services.application import ApplicationServices
from achilles.services.errors import ServiceError


class BodyLimit:
    def __init__(self, app: ASGIApp, max_bytes: int = 1048576) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        parts = []
        total = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body = message.get("body", b"")
            total += len(body)
            if total > self.max_bytes:
                await JSONResponse({"error": {"code": "PAYLOAD_TOO_LARGE"}}, status_code=413)(
                    scope, receive, send
                )
                return
            parts.append(body)
            if not message.get("more_body", False):
                break
        delivered = False

        async def bounded_receive() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": b"".join(parts), "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, send)


def create_app(
    cdp_port: int = 9222,
    token: Optional[str] = None,
    services: Optional[ApplicationServices] = None,
) -> FastAPI:
    configured_token = token or os.environ.get("ACHILLES_API_TOKEN")
    access_token = configured_token or secrets.token_urlsafe(32)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.services = services if services is not None else ApplicationServices(cdp_port)
        if not configured_token:
            print(f"Achilles local API token: {access_token}", file=sys.stderr)
        try:
            yield
        finally:
            await app.state.services.close()

    app = FastAPI(title="Achilles CDP Agent", version="2.0.0", lifespan=lifespan)
    app.add_middleware(BodyLimit)

    @app.middleware("http")
    async def local_only(request: Request, call_next: Any) -> Any:
        try:
            peer = ipaddress.ip_address(request.client.host if request.client else "0.0.0.0")
            host = request.headers.get("host", "").split(":", 1)[0]
            permitted = peer.is_loopback and host in ("127.0.0.1", "localhost")
        except ValueError:
            permitted = False
        if not permitted:
            return JSONResponse({"error": {"code": "LOOPBACK_REQUIRED"}}, status_code=403)
        if request.headers.get("origin"):
            return JSONResponse({"error": {"code": "BROWSER_ORIGIN_BLOCKED"}}, status_code=403)
        supplied = request.headers.get("authorization", "")
        if not hmac.compare_digest(
            supplied.encode("utf-8"), ("Bearer " + access_token).encode("utf-8")
        ):
            return JSONResponse({"error": {"code": "UNAUTHORIZED"}}, status_code=401)
        return await call_next(request)

    @app.exception_handler(ServiceError)
    async def service_error(request: Request, exc: ServiceError) -> JSONResponse:
        status = {
            "INVALID_ARGUMENT": 422,
            "UNKNOWN_TOOL": 404,
            "RECORD_NOT_FOUND": 404,
            "CDP_UNAVAILABLE": 503,
            "PAGE_CLOSED": 409,
            "STALE_ELEMENT_REF": 409,
        }.get(exc.code, 409)
        return JSONResponse({"error": exc.as_dict()}, status_code=status)

    @app.get("/api/tools.json")
    async def tools() -> Dict[str, Any]:
        return ApplicationServices.tools()

    @app.post("/api/tools/{name}")
    async def call(name: str, arguments: Dict[str, Any], request: Request) -> Dict[str, Any]:
        return await request.app.state.services.call(name, arguments)

    @app.get("/api/status")
    async def status(request: Request) -> Dict[str, Any]:
        return await request.app.state.services.call("browser_status", {})

    @app.get("/api/dom/tree")
    async def tree(
        request: Request, page_id: Optional[str] = None, limit: int = 200
    ) -> Dict[str, Any]:
        return await request.app.state.services.call(
            "browser_snapshot", {"page_id": page_id, "limit": limit}
        )

    @app.get("/api/security/audit")
    async def audit(request: Request, page_id: Optional[str] = None) -> Dict[str, Any]:
        return await request.app.state.services.call("security_audit", {"page_id": page_id})

    @app.get("/api/routes/apis")
    async def network(
        request: Request, page_id: Optional[str] = None, limit: int = 50
    ) -> Dict[str, Any]:
        return await request.app.state.services.call(
            "network_query", {"page_id": page_id, "limit": limit}
        )

    @app.get("/api/routes/postman")
    async def postman(request: Request) -> Dict[str, Any]:
        return await request.app.state.services.call("network_postman", {})

    @app.post("/api/action/{action}")
    async def action(request: Request, action: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return await request.app.state.services.call(
            "browser_action", {**arguments, "action": action}
        )

    return app
```

## achilles/mcp/server.py

```python
"""MCP stdio JSON-RPC para Python 3.9, sem dependência do SDK 3.10+."""

import asyncio
import json
import sys
from typing import Any, Dict, Optional, Union

from achilles.services.application import ApplicationServices
from achilles.services.errors import ServiceError

RequestId = Union[str, int]
VERSIONS = ("2025-06-18", "2024-11-05")


class MCPServer:
    def __init__(self, services: ApplicationServices) -> None:
        self.services = services
        self.initialized = False
        self.negotiated = False
        self.version = VERSIONS[0]

    @staticmethod
    def error(request_id: Any, code: int, message: str) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

    async def handle(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        request_id = request.get("id")
        method = request.get("method")
        if request.get("jsonrpc") != "2.0" or not isinstance(method, str):
            return self.error(request_id, -32600, "Invalid Request")
        params = request.get("params", {})
        if not isinstance(params, dict):
            return self.error(request_id, -32602, "Invalid params") if "id" in request else None
        if "id" not in request:
            if method == "notifications/initialized" and self.negotiated:
                self.initialized = True
            return None
        if not isinstance(request_id, (str, int)) or isinstance(request_id, bool):
            return self.error(None, -32600, "Invalid request id")
        result: Dict[str, Any]
        if method == "initialize":
            proposed = params.get("protocolVersion")
            self.version = proposed if proposed in VERSIONS else VERSIONS[0]
            self.negotiated = True
            result = {
                "protocolVersion": self.version,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "achilles-cdp", "version": "2.0.0"},
            }
        elif method == "ping":
            result = {}
        elif not self.initialized:
            return self.error(request_id, -32002, "Server not initialized")
        elif method == "tools/list":
            result = self.services.tools()
            if self.version == "2024-11-05":
                for tool in result["tools"]:
                    tool.pop("outputSchema", None)
                    tool.pop("annotations", None)
        elif method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments", {})
            if not isinstance(name, str) or not isinstance(arguments, dict):
                return self.error(request_id, -32602, "Invalid tool arguments")
            try:
                data = await self.services.call(name, arguments)
                result = {
                    "content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
                    "isError": False,
                }
                if self.version != "2024-11-05":
                    result["structuredContent"] = data
            except ServiceError as exc:
                result = {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps({"error": exc.as_dict()}, ensure_ascii=False),
                        }
                    ],
                    "isError": True,
                }
        else:
            return self.error(request_id, -32601, "Method not found")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}


async def run_mcp_stdio(cdp_port: int = 9222) -> None:
    services = ApplicationServices(cdp_port)
    server = MCPServer(services)
    pending: Dict[RequestId, asyncio.Task[Any]] = {}
    output_lock = asyncio.Lock()

    async def write(response: Dict[str, Any]) -> None:
        encoded = (json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8")
        async with output_lock:
            await asyncio.to_thread(sys.stdout.buffer.write, encoded)
            await asyncio.to_thread(sys.stdout.buffer.flush)

    async def dispatch(request: Dict[str, Any]) -> None:
        request_id = request.get("id")
        try:
            response = await server.handle(request)
            if response is not None:
                await write(response)
        except asyncio.CancelledError:
            if "id" in request:
                await write(
                    server.error(
                        request_id, -32800, "Request cancelled; observe state before retrying"
                    )
                )
        except Exception:
            if "id" in request:
                await write(server.error(request_id, -32603, "Internal error"))
        finally:
            if isinstance(request_id, (str, int)):
                pending.pop(request_id, None)

    try:
        while True:
            line = await asyncio.to_thread(sys.stdin.buffer.readline, 1048577)
            if not line:
                break
            if len(line) > 1048576:
                await write(server.error(None, -32600, "Message too large"))
                break
            try:
                request = json.loads(line)
            except (ValueError, UnicodeError):
                await write(server.error(None, -32700, "Parse error"))
                continue
            if not isinstance(request, dict):
                await write(server.error(None, -32600, "Invalid Request"))
                continue
            if request.get("method") == "notifications/cancelled":
                params = request.get("params", {})
                target = params.get("requestId") if isinstance(params, dict) else None
                if isinstance(target, (str, int)) and target in pending:
                    pending[target].cancel()
                continue
            request_id = request.get("id")
            if (
                request.get("method") in ("initialize", "notifications/initialized")
                or "id" not in request
            ):
                await dispatch(request)
            elif not isinstance(request_id, (str, int)) or isinstance(request_id, bool):
                await write(server.error(None, -32600, "Invalid request id"))
            elif request_id in pending or len(pending) >= 32:
                await write(server.error(request_id, -32000, "Duplicate id or concurrency limit"))
            else:
                pending[request_id] = asyncio.create_task(dispatch(request))
        if pending:
            _, unfinished = await asyncio.wait(list(pending.values()), timeout=10)
            for task in unfinished:
                task.cancel()
            if unfinished:
                await asyncio.gather(*unfinished, return_exceptions=True)
    finally:
        for task in list(pending.values()):
            task.cancel()
        if pending:
            await asyncio.gather(*list(pending.values()), return_exceptions=True)
        await services.close()
```

## achilles/cli/app.py

```python
"""Bootstrap leve: --help não importa transports, Pydantic ou Playwright."""

import argparse
import os
from typing import Optional, Sequence


def port(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Porta deve ser inteira") from exc
    if not 1 <= number <= 65535:
        raise argparse.ArgumentTypeError("Porta deve estar entre 1 e 65535")
    return number


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        prog="achilles", description="Achilles — Chrome CDP Application Services"
    )
    parser.add_argument("--version", action="version", version="achilles 2.0.0")
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start", help="Inicia REST autenticado em 127.0.0.1")
    start.add_argument("--port", "-p", type=port, default=8765)
    start.add_argument("--cdp-port", "-c", type=port, default=9222)
    start.add_argument("--host", choices=["127.0.0.1"], default="127.0.0.1")
    mcp = commands.add_parser("mcp", help="Inicia MCP via stdio")
    mcp.add_argument("--cdp-port", "-c", type=port, default=9222)
    args = parser.parse_args(argv)
    if args.command == "start":
        import uvicorn

        from achilles.api.server import create_app

        uvicorn.run(
            create_app(args.cdp_port, os.environ.get("ACHILLES_API_TOKEN")),
            host="127.0.0.1",
            port=args.port,
            proxy_headers=False,
            log_level="warning",
            limit_concurrency=32,
        )
    else:
        import asyncio

        from achilles.mcp.server import run_mcp_stdio

        asyncio.run(run_mcp_stdio(args.cdp_port))
```

## achilles/__init__.py

```python
"""
Achilles CDP Agent — Autonomous Agentic Chrome DevTools Protocol (CDP) Bridge & Security/API Engine
"""
__version__ = "2.0.0"
__author__ = "Pedro Lucas Reis & Reoli Open Source"
```

## setup.py

```python
"""Metadados do pacote e dependências compatíveis por versão do Python."""
from setuptools import find_namespace_packages, setup

setup(
    name="achilles-cdp",
    version="2.0.0",
    description="Chrome CDP Application Services for local AI agents",
    author="Pedro Lucas Reis & Reoli Open Source",
    packages=find_namespace_packages(include=["achilles", "achilles.*"]),
    install_requires=[
        "fastapi>=0.110,<0.129; python_version<'3.10'",
        "fastapi>=0.129,<1; python_version>='3.10'",
        "uvicorn>=0.28,<0.40; python_version<'3.10'",
        "uvicorn>=0.40,<1; python_version>='3.10'",
        "playwright>=1.49,<1.59; python_version<'3.10'",
        "playwright>=1.59,<2; python_version>='3.10'",
        "pydantic>=2.6,<3",
    ],
    extras_require={
        "test": ["httpx>=0.27,<1"],
        "build": ["pyinstaller>=6.4,<7"],
    },
    entry_points={"console_scripts": ["achilles=achilles.cli.app:main"]},
    python_requires=">=3.9",
)
```

## pyproject.toml

```toml
[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[tool.ruff]
target-version = "py39"
line-length = 100

[tool.ruff.lint]
select = ["E4", "E7", "E9", "F", "I"]
```

## requirements.txt

```text
-e .[test,build]
```

## tests/test_services.py

```python
import base64
import json
import shlex
import subprocess
import sys
import unittest
from unittest.mock import AsyncMock

from achilles.api.server import create_app
from achilles.mcp.server import MCPServer
from achilles.services.application import ApplicationServices
from achilles.services.errors import ServiceError
from achilles.services.security_engine import SecurityAuditEngine
from achilles.services.traffic_journal import TrafficJournal


def exchange() -> dict:
    return {
        "request_id": "r1",
        "page_id": "p1",
        "method": "POST",
        "url": "https://example.test:8443/api?q=a&q=b&token=private-query",
        "request_headers": {
            "authorization": "Bearer private-header",
            "cookie": "session=private-cookie",
            "content-type": "application/json",
        },
        "request_body": json.dumps({"password": "private-body", "name": "O'Brien $(echo unsafe)"}),
        "response_headers": {"set-cookie": "session=private-response"},
        "response_body": None,
        "resource_type": "document",
        "status": 200,
    }


class JournalTests(unittest.TestCase):
    def test_redacted_exports_and_quotes(self) -> None:
        r = exchange()
        curl = TrafficJournal.to_curl(r)
        parsed = shlex.split(curl)
        self.assertIn("O'Brien $(echo unsafe)", parsed[-1])
        for secret in (
            "private-query",
            "private-header",
            "private-cookie",
            "private-body",
            "private-response",
        ):
            self.assertNotIn(secret, curl)
        ps = TrafficJournal.to_curl(r, "powershell")
        self.assertIn("O''Brien", ps)
        journal = TrafficJournal()
        journal.records.append(r)
        exported = journal.postman()
        self.assertEqual(exported["item"][0]["request"]["url"]["port"], "8443")
        self.assertEqual(len(exported["item"][0]["request"]["url"]["query"]), 3)
        self.assertNotIn("private-body", json.dumps(exported))
        self.assertIn("private-body", r["request_body"])

    def test_eviction(self) -> None:
        class Request:
            method = "GET"
            url = "https://example.test/"
            resource_type = "document"
            headers = {}
            post_data = None

        journal = TrafficJournal(max_records=2)
        requests = [Request(), Request(), Request()]
        for request in requests:
            journal.request(request, "p1")
        self.assertEqual(len(journal.records), 2)
        self.assertEqual(len(journal._index), 2)
        self.assertNotIn(requests[0], journal._index)


class SecurityTests(unittest.TestCase):
    def test_missing_capture_is_not_missing_csp(self) -> None:
        result = SecurityAuditEngine.analyze("https://example.test", None, [], {}, [])
        self.assertFalse(result["findings"])
        self.assertEqual(result["coverage"]["navigation_response_headers"], "not_observed")

    def test_real_response_headers(self) -> None:
        result = SecurityAuditEngine.analyze(
            "https://example.test",
            {
                "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'",
                "Strict-Transport-Security": "max-age=31536000",
            },
            [],
            {},
            [],
        )
        self.assertFalse(result["findings"])

    def test_hs256_not_a_finding_and_jwt_redaction(self) -> None:
        def encode(data: dict) -> str:
            return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")

        token = encode({"alg": "HS256"}) + "." + encode({"exp": 2000000000}) + ".signature"
        self.assertEqual(SecurityAuditEngine.inspect_jwt(token)["issues"], [])
        bad = encode({"alg": "none"}) + "." + encode({"role": "admin"}) + "."
        result = SecurityAuditEngine.analyze("http://example.test", None, [], {"token": bad}, [])
        self.assertEqual(len(result["findings"]), 3)
        self.assertNotIn(bad, json.dumps(result))


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_mcp_catalog_parity_validation_and_notifications(self) -> None:
        app = ApplicationServices(9333)
        server = MCPServer(app)
        await server.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"},
            }
        )
        self.assertIsNone(
            await server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
        )
        result = await server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual(result["result"], app.tools())
        result = await server.handle(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "browser_status"},
            }
        )
        self.assertEqual(result["result"]["structuredContent"]["cdp_url"], "http://127.0.0.1:9333")
        with self.assertRaises(ServiceError):
            await app.call("browser_snapshot", {"limit": -1})
        with self.assertRaises(ServiceError):
            await app.call(
                "browser_action",
                {"action": "fill", "page_id": "p", "snapshot_id": "s", "element_ref": "e"},
            )
        await app.close()

    async def test_rest_auth_and_same_dispatcher(self) -> None:
        import httpx

        services = ApplicationServices(9444)
        services.call = AsyncMock(return_value={"shared": True})
        app = create_app(token="test-only-token", services=services)
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 9000))
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1"
            ) as client:
                self.assertEqual((await client.get("/api/status")).status_code, 401)
                headers = {"Authorization": "Bearer test-only-token"}
                response = await client.post("/api/tools/browser_status", json={}, headers=headers)
                self.assertEqual(response.json(), {"shared": True})
                services.call.assert_awaited_once_with("browser_status", {})
                self.assertEqual(
                    (
                        await client.get(
                            "/api/status", headers={**headers, "Origin": "https://evil.test"}
                        )
                    ).status_code,
                    403,
                )
                self.assertEqual(
                    (
                        await client.get("/api/status", headers={**headers, "Host": "evil.test"})
                    ).status_code,
                    403,
                )
                oversized = await client.post(
                    "/api/tools/browser_status", content=b"x" * 1048577, headers=headers
                )
                self.assertEqual(oversized.status_code, 413)


class ProcessTests(unittest.TestCase):
    def test_help_does_not_load_heavy_dependencies(self) -> None:
        code = "import sys; from achilles.cli.app import main;\ntry: main(['--help'])\nexcept SystemExit: pass\nassert not any(x in sys.modules for x in ('playwright','pydantic','fastapi','uvicorn'))"
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))

    def test_mcp_stdio_eof_and_protocol(self) -> None:
        messages = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"},
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "browser_status"},
            },
        ]
        result = subprocess.run(
            [sys.executable, "-m", "achilles", "mcp", "--cdp-port", "9555"],
            input="\n".join(json.dumps(m) for m in messages) + "\n",
            text=True,
            capture_output=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        responses = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(responses), 2)
        self.assertEqual(
            responses[1]["result"]["structuredContent"]["cdp_url"], "http://127.0.0.1:9555"
        )


if __name__ == "__main__":
    unittest.main()
```

## tests/test_browser_integration.py

```python
"""Integração isolada: Chrome descartável, fixture HTTP local e nenhum site externo."""

import asyncio
import json
import os
import socket
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from achilles.services.application import ApplicationServices
from achilles.services.errors import ServiceError

HTML = b"""<!doctype html><html><head><title>Fixture</title></head><body>
<label for="name">Name</label><input id="name" value="old">
<button id="save" onclick="document.body.dataset.clicked='yes'">Save</button>
<button disabled>Disabled</button><select aria-label="Choice"><option value="a">A</option><option value="b">B</option></select>
<div id="host"></div><iframe src="/frame"></iframe>
<script>document.querySelector('#host').attachShadow({mode:'open'}).innerHTML='<button aria-label="Shadow">Inside</button>';</script>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/frame":
            body = (
                b'<html><body><button>Frame</button><iframe src="/nested"></iframe></body></html>'
            )
        elif self.path == "/nested":
            body = b'<html><body><input aria-label="Nested"></body></html>'
        elif self.path.startswith("/api"):
            body = b'{"ok":true,"password":"fixture-password"}'
        else:
            body = HTML
        self.send_response(200)
        self.send_header(
            "Content-Type", "application/json" if self.path.startswith("/api") else "text/html"
        )
        self.send_header("Content-Length", str(len(body)))
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline'; frame-ancestors 'self'",
        )
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


@unittest.skipUnless(
    os.environ.get("ACHILLES_BROWSER_TESTS") == "1",
    "Set ACHILLES_BROWSER_TESTS=1 for isolated Chromium tests",
)
class BrowserTests(unittest.IsolatedAsyncioTestCase):
    async def test_snapshot_actions_traffic_reconnect_attach(self) -> None:
        from playwright.async_api import async_playwright

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            cdp_port = sock.getsockname()[1]
        owner = await async_playwright().start()
        browser = await owner.chromium.launch(
            headless=True, args=[f"--remote-debugging-port={cdp_port}"]
        )
        context = await browser.new_context()
        owned_page = await context.new_page()
        app = ApplicationServices(cdp_port)
        try:
            await asyncio.gather(*(app.session.connect() for _ in range(5)))
            self.assertEqual(app.session.generation, 1)
            page_id, page = await app.session.page()
            url = f"http://127.0.0.1:{server.server_port}"
            await page.goto(url)
            await (
                page.frame_locator("iframe")
                .frame_locator("iframe")
                .get_by_label("Nested")
                .wait_for()
            )
            snapshot = await app.observations.snapshot(page_id)
            names = {e["name"] for e in snapshot["elements"]}
            self.assertIn("chrome_ax", snapshot["accessibility"])
            self.assertTrue({"Name", "Save", "Shadow", "Frame", "Nested"}.issubset(names), names)

            async def act(name: str, action: str, value: str = "") -> dict:
                snap = await app.observations.snapshot(page_id)
                target = next(e for e in snap["elements"] if e["name"] == name)
                return await app.actions.execute(
                    action, snap["snapshot_id"], target["element_ref"], page_id, value
                )

            await act("Name", "fill", "replacement")
            self.assertEqual(await page.locator("#name").input_value(), "replacement")
            await act("Shadow", "click")
            await act("Frame", "hover")
            await act("Nested", "fill", "nested value")
            await act("Name", "press", "Tab")
            await act("Choice", "select", "b")
            self.assertEqual(await page.get_by_label("Choice").input_value(), "b")
            result = await act("Save", "click")
            self.assertEqual(result["status"], "executed")
            self.assertEqual(result["verification"]["status"], "observed")
            self.assertEqual(await page.get_attribute("body", "data-clicked"), "yes")
            with self.assertRaises(ServiceError) as failed:
                snap = await app.observations.snapshot(page_id)
                target = next(e for e in snap["elements"] if e["name"] == "Disabled")
                await app.actions.execute(
                    "click", snap["snapshot_id"], target["element_ref"], page_id, timeout_ms=100
                )
            self.assertEqual(failed.exception.code, "TARGET_NOT_ACTIONABLE")
            snap = await app.observations.snapshot(page_id)
            target = next(e for e in snap["elements"] if e["name"] == "Save")
            await page.evaluate(
                "document.querySelector('#save').outerHTML='<button id=save>Save</button>'"
            )
            with self.assertRaises(ServiceError) as stale:
                await app.actions.execute(
                    "click", snap["snapshot_id"], target["element_ref"], page_id
                )
            self.assertEqual(stale.exception.code, "STALE_ELEMENT_REF")
            await page.evaluate("fetch('/api?token=fixture-token').then(r=>r.json())")
            await app.session.drain()
            records = app.journal.query(100)
            api = next(r for r in records if "/api?" in r["url"])
            self.assertEqual(api["status"], 200)
            self.assertEqual(api["body_state"], "captured")
            self.assertNotIn("fixture-password", json.dumps(api))
            self.assertNotIn("fixture-token", api["url"])
            audit = await app.security.audit(page_id)
            self.assertEqual(audit["coverage"]["navigation_response_headers"], "observed")
            self.assertNotIn("CSP_MISSING", {f["rule_id"] for f in audit["findings"]})
            popup = await context.new_page()
            await popup.goto(url)
            targets = await app.session.list_pages()
            self.assertGreaterEqual(len(targets["pages"]), 2)
            await app.session.select_page(page_id)
            self.assertEqual(app.session.registry.active_page_id, page_id)
            # Desconexão do cliente attach mantém o Chrome do proprietário vivo.
            await app.session.close()
            self.assertTrue(browser.is_connected())
            self.assertFalse(owned_page.is_closed())
            await app.session.connect()
            self.assertEqual(app.session.generation, 2)
            await browser.close()
            browser = await owner.chromium.launch(
                headless=True, args=[f"--remote-debugging-port={cdp_port}"]
            )
            replacement = await browser.new_context()
            await replacement.new_page()
            await app.session.connect()
            self.assertEqual(app.session.generation, 3)
            with self.assertRaises(ServiceError) as closed:
                await app.session.page(page_id)
            self.assertEqual(closed.exception.code, "PAGE_CLOSED")
        finally:
            await app.close()
            await browser.close()
            await owner.stop()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
```
