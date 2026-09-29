"""Conexão CDP em modo attach e registro de targets por sessão."""

import asyncio
import inspect
import logging
import random
import uuid
from collections import deque
from typing import TYPE_CHECKING, Any, Callable, Deque, Dict, List, Optional, Set, Tuple
from urllib.parse import urlsplit

from .errors import ServiceError
from .redaction import redact, redact_url
from .traffic_journal import TrafficJournal

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Frame, Page, Playwright

LOG = logging.getLogger(__name__)

STEALTH_SCRIPT = """
(() => {
    try {
        // 1. Mask navigator.webdriver
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
            configurable: true
        });

        // 2. Mock Chrome runtime APIs
        if (!window.chrome) {
            window.chrome = {};
        }
        if (!window.chrome.runtime) {
            window.chrome.runtime = {};
        }
        if (!window.chrome.loadTimes) {
            window.chrome.loadTimes = function() {};
        }
        if (!window.chrome.csi) {
            window.chrome.csi = function() {};
        }
        if (!window.chrome.app) {
            window.chrome.app = {};
        }

        // 3. Spoof Notification permission
        if (window.Notification && Notification.permission === 'default') {
            Object.defineProperty(Notification, 'permission', {
                get: () => 'default',
                configurable: true
            });
        }

        // 4. Hardware metrics consistency
        if (!navigator.hardwareConcurrency || navigator.hardwareConcurrency < 4) {
            Object.defineProperty(navigator, 'hardwareConcurrency', {
                get: () => 8,
                configurable: true
            });
        }
        if (!navigator.deviceMemory || navigator.deviceMemory < 4) {
            Object.defineProperty(navigator, 'deviceMemory', {
                get: () => 8,
                configurable: true
            });
        }

        // 5. Plugin array emulation
        if (navigator.plugins && navigator.plugins.length === 0) {
            const mockPlugins = [
                { name: 'PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                { name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                { name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' }
            ];
            Object.defineProperty(navigator, 'plugins', {
                get: () => mockPlugins,
                configurable: true
            });
        }

        // 6. WebGL Unmasked Vendor & Renderer Spoofing
        const getParameterWrapper = (original) => function(parameter) {
            if (parameter === 37445) { // UNMASKED_VENDOR_WEBGL
                return 'Google Inc. (NVIDIA)';
            }
            if (parameter === 37446) { // UNMASKED_RENDERER_WEBGL
                return 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)';
            }
            return original.call(this, parameter);
        };

        if (window.WebGLRenderingContext) {
            const origGetParam = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = getParameterWrapper(origGetParam);
        }
        if (window.WebGL2RenderingContext) {
            const origGetParam2 = WebGL2RenderingContext.prototype.getParameter;
            WebGL2RenderingContext.prototype.getParameter = getParameterWrapper(origGetParam2);
        }

        // 7. Canvas Fingerprint Micro-Noise
        if (window.CanvasRenderingContext2D) {
            const origGetImageData = CanvasRenderingContext2D.prototype.getImageData;
            CanvasRenderingContext2D.prototype.getImageData = function(sx, sy, sw, sh, settings) {
                const imageData = origGetImageData.call(this, sx, sy, sw, sh, settings);
                if (imageData && imageData.data && imageData.data.length > 4) {
                    // Micro-shift least significant bit of first pixel
                    imageData.data[0] = (imageData.data[0] ^ 1);
                }
                return imageData;
            };
        }

        // 8. Web Audio API Acoustic Micro-Jitter
        if (window.AudioBuffer) {
            const origGetChannelData = AudioBuffer.prototype.getChannelData;
            AudioBuffer.prototype.getChannelData = function(channel) {
                const data = origGetChannelData.call(this, channel);
                if (data && data.length > 10) {
                    data[0] += 0.0000001;
                }
                return data;
            };
        }
    } catch (e) {}
})();
"""


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
        self.cdp_port = cdp_port
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

    @property
    def browser(self) -> Optional["Browser"]:
        return self._browser

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
            return None

    def _track_page(self, page: "Page") -> str:
        page_id = self.registry.add(page)
        if id(page) not in self._pages:
            self._pages.add(id(page))
            self._spawn(lambda: page.add_init_script(STEALTH_SCRIPT))
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
        self._spawn(lambda: context.add_init_script(STEALTH_SCRIPT))
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
        if self._playwright is not None:
            await self._playwright.stop()
        self._playwright = None
        self._browser = None
        self._contexts.clear()
        self._pages.clear()
        self.registry = TargetRegistry()
        await asyncio.sleep(0.05)

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
                    if attempt == 0:
                        from .chrome_launcher import ensure_chrome_running
                        await asyncio.to_thread(ensure_chrome_running, self.cdp_port)
                    self._playwright = await async_playwright().start()
                    connect = self._playwright.chromium.connect_over_cdp
                    options: Dict[str, Any] = {"timeout": self.connect_timeout_ms}
                    if "no_defaults" in inspect.signature(connect).parameters:
                        options["no_defaults"] = True
                    self._browser = await connect(self.cdp_url, **options)
                    self._listen(
                        self._browser,
                        "disconnected",
                        lambda: LOG.info("Navegador CDP desconectado; reconexão na próxima operação"),
                    )
                    self.generation += 1
                    for context in self._browser.contexts:
                        self._track_context(context)
                        try:
                            await context.add_init_script(STEALTH_SCRIPT)
                        except Exception:
                            pass
                    return
                except Exception as exc:
                    await self._cleanup()
                    if attempt + 1 == self.attempts:
                        raise ServiceError(
                            "CDP_UNAVAILABLE", "Navegador CDP indisponível na porta configurada.", True
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
            "active_page_id": self.registry.active_page_id,
            "generation": self.generation,
            "selection_policy": "explicit_or_latest_discovered",
        }

    async def new_page(self, url: Optional[str] = None) -> Dict[str, Any]:
        await self.connect()
        if self._browser is None:
            raise ServiceError("CDP_UNAVAILABLE", "Navegador CDP indisponível.")
        context = self._browser.contexts[0] if self._browser.contexts else await self._browser.new_context()
        page = await context.new_page()
        key = self._track_page(page)
        self.registry.active_page_id = key
        target_url = url or "about:blank"
        if url:
            await self.navigate(target_url, page_id=key)
        title = ""
        try:
            title = await page.title()
        except Exception:
            pass
        return {
            "status": "created",
            "page_id": key,
            "url": redact_url(page.url),
            "title": redact(title),
        }

    async def close_page(self, page_id: Optional[str] = None) -> Dict[str, Any]:
        key, page = await self.page(page_id)
        if not page.is_closed():
            try:
                await page.close()
            except Exception:
                pass
        self.registry.remove(page)
        return {
            "status": "closed",
            "closed_page_id": key,
            "active_page_id": self.registry.active_page_id,
        }

    async def select_page(self, page_id: str) -> Dict[str, Any]:
        key, page = await self.page(page_id)
        await page.bring_to_front()
        self.registry.active_page_id = key
        return {"page_id": key, "url": redact_url(page.url)}

    async def navigate(
        self,
        url: str,
        page_id: Optional[str] = None,
        wait_until: str = "domcontentloaded",
        timeout_ms: int = 15000,
    ) -> Dict[str, Any]:
        parsed = urlsplit(url)
        scheme = parsed.scheme.lower() if parsed.scheme else ""
        if scheme not in ("http", "https", "about"):
            raise ServiceError(
                "INVALID_ARGUMENT",
                f"Esquema de URL '{scheme or 'nenhum'}' bloqueado por segurança. Permitidos: http, https, about.",
            )

        key, page = await self.page(page_id)
        async with self.registry.locks[key]:
            from playwright.async_api import Error as PlaywrightError
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError
            try:
                valid_wait = wait_until if wait_until in ("load", "domcontentloaded", "networkidle", "commit") else "domcontentloaded"
                response = await page.goto(url, wait_until=valid_wait, timeout=timeout_ms)  # type: ignore[arg-type]
                status_code = response.status if response else 200
            except PlaywrightTimeoutError as exc:
                raise ServiceError("OPERATION_TIMEOUT", "A navegação excedeu o tempo limite estipulado.") from exc
            except PlaywrightError as exc:
                raise ServiceError("NAVIGATION_ERROR", f"Falha ao navegar: {str(exc)}") from exc

            title = ""
            try:
                title = await page.title()
            except Exception:
                pass

            return {
                "status": "navigated",
                "page_id": key,
                "url": redact_url(page.url),
                "http_status": status_code,
                "title": redact(title),
            }

    async def scroll(
        self,
        direction: str = "down",
        amount: int = 500,
        selector: Optional[str] = None,
        page_id: Optional[str] = None,
        timeout_ms: int = 5000,
    ) -> Dict[str, Any]:
        key, page = await self.page(page_id)
        async with self.registry.locks[key]:
            try:
                script = """({direction, amount, selector}) => {
                    let target = selector ? document.querySelector(selector) : (document.scrollingElement || document.documentElement || document.body);
                    if (!target) return { scrolled: false, error: 'Container não encontrado' };
                    
                    let prevY = target.scrollTop !== undefined ? target.scrollTop : window.scrollY;
                    if (direction === 'down') {
                        if (selector) target.scrollTop += amount; else window.scrollBy(0, amount);
                    } else if (direction === 'up') {
                        if (selector) target.scrollTop -= amount; else window.scrollBy(0, -amount);
                    } else if (direction === 'top') {
                        if (selector) target.scrollTop = 0; else window.scrollTo(0, 0);
                    } else if (direction === 'bottom') {
                        if (selector) target.scrollTop = target.scrollHeight; else window.scrollTo(0, document.body.scrollHeight);
                    }
                    let newY = target.scrollTop !== undefined ? target.scrollTop : window.scrollY;
                    return { scrolled: true, previous_y: prevY, current_y: newY, delta: newY - prevY };
                }"""
                res = await page.evaluate(script, {"direction": direction, "amount": amount, "selector": selector})
                await asyncio.sleep(0.3)
                return {
                    "status": "scrolled",
                    "page_id": key,
                    "direction": direction,
                    "details": res,
                    "url": redact_url(page.url),
                }
            except Exception as exc:
                raise ServiceError("SCROLL_ERROR", f"Falha ao rolar a página: {str(exc)}") from exc

    async def drain(self) -> None:
        tasks = list(self._tasks)
        if tasks:
            await asyncio.wait(tasks, timeout=6)

    async def close(self) -> None:
        async with self._connection_lock():
            await self._cleanup()
