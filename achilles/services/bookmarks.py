"""Bookmark operations through the browser's own extension API."""

import asyncio
from typing import TYPE_CHECKING, Any, Dict, Optional
from urllib.parse import urlsplit

from .errors import ServiceError
from .redaction import redact, redact_url

if TYPE_CHECKING:
    from .session_manager import BrowserSessionManager


EXTENSION_ID = "iaheffblcnihpbdecmnkioimgdjjffgo"
BRIDGE_URL = "chrome-extension://%s/bridge.html" % EXTENSION_ID

BOOKMARK_SCRIPT = """async ({operation, arguments}) => {
  const api = globalThis.chrome && chrome.bookmarks;
  if (!api) return {error: 'BRIDGE_UNAVAILABLE'};
  try {
    let result;
    if (operation === 'list') {
      result = arguments.parent_id
        ? await api.getChildren(arguments.parent_id)
        : (await api.getTree())[0].children || [];
    } else if (operation === 'search') {
      result = await api.search(arguments.query);
    } else if (operation === 'create') {
      let parentId = arguments.parent_id;
      if (!parentId) {
        const root = (await api.getTree())[0];
        const bar = (root.children || []).find(node => node.folderType === 'bookmarks-bar')
          || (root.children || []).find(node => !node.url);
        if (!bar) throw new Error('No writable bookmark folder found');
        parentId = bar.id;
      }
      result = await api.create({parentId, title: arguments.title, url: arguments.url});
    } else if (operation === 'update') {
      const changes = {};
      if (arguments.title !== null) changes.title = arguments.title;
      if (arguments.url !== null) changes.url = arguments.url;
      result = await api.update(arguments.id, changes);
    } else if (operation === 'remove') {
      await api.remove(arguments.id);
      result = {id: arguments.id, removed: true};
    }
    return {result};
  } catch (error) {
    return {error: 'BOOKMARK_OPERATION_FAILED', message: String(error?.message || error)};
  }
}"""


def _safe_node(node: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(node.get("id", "")),
        "parent_id": node.get("parentId"),
        "title": redact(node.get("title", "")),
        "url": redact_url(node["url"]) if node.get("url") else None,
        "index": node.get("index"),
        "folder_type": node.get("folderType"),
    }


def validate_bookmark_url(url: str) -> str:
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise ServiceError("INVALID_ARGUMENT", "URL de favorito inválida.") from exc
    if parts.scheme not in ("http", "https") or not parts.netloc or parts.username or parts.password:
        raise ServiceError("INVALID_ARGUMENT", "Favoritos aceitam apenas URLs HTTP(S) sem credenciais.")
    return url


class BookmarkService:
    def __init__(self, session: "BrowserSessionManager") -> None:
        self.session = session
        self._lock: Optional[asyncio.Lock] = None

    def _operation_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def call(self, operation: str, **arguments: Any) -> Dict[str, Any]:
        if operation in ("create", "update") and arguments.get("url") is not None:
            validate_bookmark_url(arguments["url"])
        async with self._operation_lock():
            await self.session.connect()
            browser = self.session.browser
            if browser is None or not browser.contexts:
                raise ServiceError("BOOKMARK_BRIDGE_UNAVAILABLE", "Perfil CDP indisponível para favoritos.")
            previous_page = self.session.registry.active_page_id
            page = await browser.contexts[0].new_page()
            try:
                await page.goto(BRIDGE_URL, wait_until="domcontentloaded", timeout=5000)
                response = await page.evaluate(
                    BOOKMARK_SCRIPT, {"operation": operation, "arguments": arguments}
                )
            except Exception as exc:
                raise ServiceError(
                    "BOOKMARK_BRIDGE_UNAVAILABLE",
                    "Instale a extensão Achilles Browser Bridge neste perfil Chrome/Edge.",
                ) from exc
            finally:
                await page.close()
                if previous_page in self.session.registry.pages:
                    self.session.registry.active_page_id = previous_page
            if response.get("error") == "BRIDGE_UNAVAILABLE":
                raise ServiceError(
                    "BOOKMARK_BRIDGE_UNAVAILABLE",
                    "Instale a extensão Achilles Browser Bridge neste perfil Chrome/Edge.",
                )
            if response.get("error"):
                raise ServiceError("BOOKMARK_OPERATION_FAILED", "O navegador recusou a operação em favoritos.")
            result = response.get("result")
            if operation in ("list", "search"):
                limit = arguments["limit"]
                return {
                    "bookmarks": [_safe_node(node) for node in result[:limit]],
                    "total": len(result),
                    "truncated": len(result) > limit,
                }
            if operation == "remove":
                return result
            return {"bookmark": _safe_node(result)}
