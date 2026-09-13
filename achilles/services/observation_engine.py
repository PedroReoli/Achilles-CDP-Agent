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
            const testId = el.getAttribute('data-testid') || el.getAttribute('data-test') || el.getAttribute('data-automation-id') || (el.id ? '#' + el.id : null);
            const ariaLabel = el.getAttribute('aria-label');
            const selectorHint = testId ? (testId.startsWith('#') ? testId : `[data-testid="${testId}"]`) : (ariaLabel ? `[aria-label="${ariaLabel.slice(0, 40)}"]` : (name ? `${el.localName}:has-text("${name.slice(0, 30)}")` : el.localName));
            result.push({node_ref:ref, role, name, tag:el.localName, type:el.type || '',
                selector_hint: selectorHint,
                test_id: testId,
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
                    continue
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
                    pass
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
                    "selector_hint": item.get("selector_hint", ""),
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
                continue
        self.snapshots.clear()
        self._signatures.clear()
