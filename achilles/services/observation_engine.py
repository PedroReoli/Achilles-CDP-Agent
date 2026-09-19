"""Snapshots limitados, identidade por nó e observação de frames/shadow roots."""

import asyncio
import json
import uuid
from collections import OrderedDict
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .challenge_engine import EVALUATE_CHALLENGE_JS
from .errors import ServiceError
from .hud import HudManager
from .redaction import redact, redact_url
from .session_manager import BrowserSessionManager

if TYPE_CHECKING:
    from playwright.async_api import Page


READER_EXTRACT = r"""() => {
    const candidates = [
        'article', '[role="main"]', 'main', '#main', '#content',
        '.post-content', '.article-content', '.entry-content', '.content', 'body'
    ];
    let root = null;
    for (const sel of candidates) {
        const el = document.querySelector(sel);
        if (el && el.innerText && el.innerText.trim().length > 100) {
            root = el;
            break;
        }
    }
    if (!root) root = document.body || document.documentElement;

    const clone = root.cloneNode(true);
    const noiseSelectors = [
        'script', 'style', 'noscript', 'nav', 'header', 'footer', 'aside',
        'iframe', 'svg', 'canvas', 'video', 'audio',
        '[role="banner"]', '[role="navigation"]', '[role="complementary"]',
        '[role="dialog"]', '[role="alertdialog"]',
        '.ad', '.ads', '.advertisement', '.social-share', '.share-buttons',
        '.cookie-banner', '.cookie-consent', '#cookie-notice',
        '[aria-hidden="true"]'
    ];
    for (const sel of noiseSelectors) {
        for (const el of clone.querySelectorAll(sel)) {
            el.remove();
        }
    }

    function toMarkdown(node) {
        if (!node) return '';
        if (node.nodeType === Node.TEXT_NODE) {
            return node.textContent ? node.textContent.replace(/\s+/g, ' ') : '';
        }
        if (node.nodeType !== Node.ELEMENT_NODE) return '';

        const tag = node.tagName.toLowerCase();
        let childrenMd = Array.from(node.childNodes).map(toMarkdown).join('');

        if (['h1', 'h2', 'h3', 'h4', 'h5', 'h6'].includes(tag)) {
            const level = parseInt(tag[1], 10);
            const prefix = '#'.repeat(level);
            return `\n\n${prefix} ${childrenMd.trim()}\n\n`;
        }
        if (tag === 'p') {
            const text = childrenMd.trim();
            return text ? `\n\n${text}\n\n` : '';
        }
        if (tag === 'blockquote') {
            const lines = childrenMd.trim().split('\n').map(l => `> ${l}`).join('\n');
            return `\n\n${lines}\n\n`;
        }
        if (tag === 'ul') {
            return `\n\n${childrenMd.trim()}\n\n`;
        }
        if (tag === 'ol') {
            return `\n\n${childrenMd.trim()}\n\n`;
        }
        if (tag === 'li') {
            return `* ${childrenMd.trim()}\n`;
        }
        if (tag === 'pre') {
            return `\n\n\`\`\`\n${node.textContent.trim()}\n\`\`\`\n\n`;
        }
        if (tag === 'code') {
            if (node.parentElement && node.parentElement.tagName.toLowerCase() === 'pre') {
                return node.textContent;
            }
            return `\`${childrenMd.trim()}\``;
        }
        if (tag === 'a') {
            const href = node.getAttribute('href');
            const text = childrenMd.trim();
            if (text && href && !href.startsWith('javascript:') && !href.startsWith('#')) {
                try {
                    const absUrl = new URL(href, window.location.href).href;
                    return `[${text}](${absUrl})`;
                } catch(e) {
                    return `[${text}](${href})`;
                }
            }
            return text;
        }
        if (tag === 'table') {
            const rows = Array.from(node.querySelectorAll('tr'));
            if (!rows.length) return '';
            let tableMd = '\n\n';
            rows.forEach((tr, i) => {
                const cells = Array.from(tr.querySelectorAll('th, td')).map(c => c.textContent.trim().replace(/\|/g, '\\|'));
                if (cells.length > 0) {
                    tableMd += '| ' + cells.join(' | ') + ' |\n';
                    if (i === 0) {
                        tableMd += '| ' + cells.map(() => '---').join(' | ') + ' |\n';
                    }
                }
            });
            return tableMd + '\n\n';
        }
        if (tag === 'hr') {
            return '\n\n---\n\n';
        }
        if (tag === 'br') {
            return '\n';
        }
        if (['strong', 'b'].includes(tag)) {
            const text = childrenMd.trim();
            return text ? ` **${text}** ` : '';
        }
        if (['em', 'i'].includes(tag)) {
            const text = childrenMd.trim();
            return text ? ` *${text}* ` : '';
        }
        return childrenMd;
    }

    let markdown = toMarkdown(clone);
    markdown = markdown.replace(/\n{3,}/g, '\n\n').trim();

    const title = document.title || (document.querySelector('h1') ? document.querySelector('h1').innerText.trim() : '');
    const metaDesc = document.querySelector('meta[name="description"]')?.getAttribute('content') || '';
    const rawLength = (document.documentElement ? document.documentElement.outerHTML.length : 0);

    return {
        title: title.trim(),
        description: metaDesc.trim(),
        markdown: markdown,
        raw_chars: rawLength,
        content_chars: markdown.length
    };
}"""


EXTRACT = r"""({key, attribute, limit, in_viewport_only, selector}) => {
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
        const queryRoot = (selector && root.querySelector) ? (root.querySelector(selector) || root) : root;
        const targetElements = queryRoot.querySelectorAll ? queryRoot.querySelectorAll('*') : [];
        for (const el of targetElements) {
            if (++visited > 20000 || result.length >= limit) { truncated = true; return; }
            if (el.shadowRoot) walk(el.shadowRoot);
            const role = el.getAttribute('role')?.split(' ')[0] || implicit(el);
            if (!role || ['none','presentation'].includes(role) || el.type === 'hidden') continue;
            const rect = el.getBoundingClientRect(), style = getComputedStyle(el);
            if (!rect.width || !rect.height || style.display === 'none' || style.visibility === 'hidden'
                || el.closest('[aria-hidden="true"], [inert]')) continue;
            const in_viewport = rect.bottom > 0 && rect.right > 0 && rect.top < innerHeight && rect.left < innerWidth;
            if (in_viewport_only && !in_viewport) continue;
            let ref = state.nodes.get(el);
            if (!ref) {
                ref = state.epoch + '_' + (++state.counter);
                state.nodes.set(el, ref);
                try { el.setAttribute(attribute, ref); } catch(e) {}
            }
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
                in_viewport: in_viewport});
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
        self.total_raw_chars: int = 0
        self.total_compact_chars: int = 0
        self.total_reads: int = 0
        self.total_snapshots: int = 0

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

    async def snapshot(
        self,
        page_id: Optional[str] = None,
        limit: int = 200,
        format: str = "compact",
        in_viewport_only: bool = True,
        selector: Optional[str] = None,
    ) -> Dict[str, Any]:
        key, page = await self.session.page(page_id)
        async with self.session.registry.locks[key]:
            return await self.capture(
                key,
                page,
                limit,
                include_ax=True,
                format=format,
                in_viewport_only=in_viewport_only,
                selector=selector,
            )

    async def capture(
        self,
        page_id: str,
        page: "Page",
        limit: int = 200,
        include_ax: bool = True,
        format: str = "compact",
        in_viewport_only: bool = True,
        selector: Optional[str] = None,
    ) -> Dict[str, Any]:
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
                        "in_viewport_only": in_viewport_only,
                        "selector": selector,
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
        accessibility = await self._accessibility(page, elements) if include_ax else "fast_dom"
        try:
            challenge_check = await page.evaluate(EVALUATE_CHALLENGE_JS)
            if challenge_check.get("detected"):
                warnings.append({
                    "code": "HUMAN_CHALLENGE_DETECTED",
                    "type": challenge_check.get("type"),
                    "name": challenge_check.get("name"),
                    "message": challenge_check.get("description"),
                })
                await HudManager.update(
                    page,
                    status="waiting_human",
                    message=f"Atenção: {challenge_check.get('name')}",
                )
            else:
                await HudManager.update(page, status="idle", message="Achilles ativo")
        except Exception:
            pass

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
        
        pub = self.public(snapshot, fmt=format)
        compact_len = len(pub.get("compact", ""))
        raw_dom_est = max(compact_len * 6, 2000)
        self.total_raw_chars += raw_dom_est
        self.total_compact_chars += compact_len
        self.total_snapshots += 1
        saved_pct = round((1.0 - (compact_len / max(1, raw_dom_est))) * 100, 1)
        pub["tokens_saved_percent"] = f"{saved_pct}%"
        return pub

    @staticmethod
    def public(snapshot: Dict[str, Any], fmt: str = "compact") -> Dict[str, Any]:
        result = redact(snapshot)
        lines = []
        for e in result.get("elements", []):
            ref = f"[@{e['element_ref']}]"
            role = e.get("role", "element")
            name = json.dumps(e.get("name", ""), ensure_ascii=False)
            details = []
            if e.get("test_id"):
                details.append(f"id={e['test_id']}")
            elif e.get("selector_hint"):
                details.append(f"hint={e['selector_hint']}")
            if e.get("disabled"):
                details.append("disabled")
            if e.get("checked") is not None:
                details.append(f"checked={e['checked']}")
            if e.get("expanded") is not None:
                details.append(f"expanded={e['expanded']}")
            detail_str = f" ({', '.join(details)})" if details else ""
            lines.append(f"{ref} {role} {name}{detail_str}")
        result["compact"] = "\n".join(lines)
        if fmt == "compact":
            result["text"] = result["compact"]
        return result

    async def read_content(
        self, page_id: Optional[str] = None, max_length: int = 50000
    ) -> Dict[str, Any]:
        key, page = await self.session.page(page_id)
        if page.is_closed():
            raise ServiceError("PAGE_CLOSED", "A aba foi fechada.")
        async with self.session.registry.locks[key]:
            try:
                extracted = await page.evaluate(READER_EXTRACT)
            except Exception as exc:
                raise ServiceError(
                    "READ_ERROR", f"Falha ao extrair conteúdo legível: {type(exc).__name__}"
                ) from exc

            raw_chars = int(extracted.get("raw_chars", 0))
            md = extracted.get("markdown", "")
            if len(md) > max_length:
                md = md[:max_length] + "\n\n... [CONTEÚDO TRUNCADO PELO LIMITE]"
            content_chars = len(md)

            saved_pct = (
                round((1.0 - (content_chars / max(1, raw_chars))) * 100, 1)
                if raw_chars > 0
                else 0.0
            )

            self.total_raw_chars += raw_chars
            self.total_compact_chars += content_chars
            self.total_reads += 1

            result = {
                "page_id": key,
                "url": redact_url(page.url),
                "title": redact(extracted.get("title", "")),
                "description": redact(extracted.get("description", "")),
                "markdown": redact(md),
                "metrics": {
                    "raw_html_chars": raw_chars,
                    "extracted_chars": content_chars,
                    "estimated_raw_tokens": raw_chars // 4,
                    "estimated_extracted_tokens": content_chars // 4,
                    "tokens_saved_percent": f"{saved_pct}%",
                },
            }
            return result

    def get_token_metrics(self) -> Dict[str, Any]:
        raw = self.total_raw_chars
        compact = self.total_compact_chars
        saved = max(0, raw - compact)
        pct = round((1.0 - (compact / max(1, raw))) * 100, 1) if raw > 0 else 0.0
        return {
            "total_reads": self.total_reads,
            "total_snapshots": self.total_snapshots,
            "raw_chars_avoided": saved,
            "raw_tokens_avoided": saved // 4,
            "tokens_consumed_estimated": compact // 4,
            "overall_savings_percent": f"{pct}%",
        }

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
