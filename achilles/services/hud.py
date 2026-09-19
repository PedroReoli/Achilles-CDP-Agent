"""In-browser Floating HUD Overlay (Closed Shadow DOM) para transparência de navegação."""

import logging
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from playwright.async_api import Page

LOG = logging.getLogger(__name__)

HUD_SCRIPT = r"""({status, message}) => {
    try {
        let host = document.getElementById('__achilles_hud_host__');
        let shadow = host ? host._achilles_shadow : null;

        if (!host) {
            host = document.createElement('div');
            host.id = '__achilles_hud_host__';
            host.style.cssText = 'position: fixed; top: 14px; right: 14px; z-index: 2147483647; pointer-events: none; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;';
            
            shadow = host.attachShadow({mode: 'closed'});
            host._achilles_shadow = shadow;

            const style = document.createElement('style');
            style.textContent = `
                .achilles-pill {
                    pointer-events: auto;
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    padding: 6px 14px;
                    background: rgba(15, 23, 42, 0.85);
                    backdrop-filter: blur(12px);
                    -webkit-backdrop-filter: blur(12px);
                    border: 1px solid rgba(168, 85, 247, 0.35);
                    border-radius: 9999px;
                    color: #f8fafc;
                    font-size: 12px;
                    font-weight: 500;
                    box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
                    transition: all 0.3s ease;
                    user-select: none;
                }
                .achilles-pill:hover {
                    border-color: rgba(168, 85, 247, 0.7);
                    box-shadow: 0 8px 32px 0 rgba(168, 85, 247, 0.25);
                }
                .dot {
                    width: 8px;
                    height: 8px;
                    border-radius: 50%;
                    background: #22c55e;
                    box-shadow: 0 0 8px #22c55e;
                }
                .dot.acting {
                    background: #c084fc;
                    box-shadow: 0 0 10px #c084fc;
                    animation: pulse 1.2s infinite;
                }
                .dot.waiting_human {
                    background: #f59e0b;
                    box-shadow: 0 0 12px #f59e0b;
                    animation: pulse 0.8s infinite;
                }
                @keyframes pulse {
                    0%, 100% { opacity: 1; transform: scale(1); }
                    50% { opacity: 0.4; transform: scale(1.3); }
                }
                .brand {
                    font-weight: 700;
                    color: #c084fc;
                    letter-spacing: 0.5px;
                }
                .text {
                    color: #e2e8f0;
                    max-width: 260px;
                    overflow: hidden;
                    text-overflow: ellipsis;
                    white-space: nowrap;
                }
                .btn-toggle {
                    cursor: pointer;
                    background: transparent;
                    border: none;
                    color: #94a3b8;
                    font-size: 11px;
                    padding: 0 2px;
                    display: flex;
                    align-items: center;
                }
                .btn-toggle:hover {
                    color: #f8fafc;
                }
                .minimized .text, .minimized .brand {
                    display: none;
                }
            `;
            shadow.appendChild(style);

            const container = document.createElement('div');
            container.className = 'achilles-pill';
            container.id = 'achilles-pill-container';
            container.innerHTML = `
                <div class="dot" id="achilles-dot"></div>
                <span class="brand">ACHILLES</span>
                <span class="text" id="achilles-text">${message || 'Modo Colaborativo'}</span>
                <button class="btn-toggle" id="achilles-btn" title="Minimizar">_</button>
            `;
            shadow.appendChild(container);

            const btn = container.querySelector('#achilles-btn');
            btn.onclick = () => {
                container.classList.toggle('minimized');
                btn.textContent = container.classList.contains('minimized') ? '+' : '_';
            };

            (document.body || document.documentElement).appendChild(host);
        }

        if (shadow) {
            const dot = shadow.getElementById('achilles-dot');
            const text = shadow.getElementById('achilles-text');
            if (dot) {
                dot.className = 'dot ' + (status || 'idle');
            }
            if (text && message) {
                text.textContent = message;
            }
        }
        return true;
    } catch(e) {
        return false;
    }
}"""


class HudManager:
    """Injeta e atualiza o Floating HUD no navegador."""

    @staticmethod
    async def update(page: "Page", status: str = "idle", message: str = "") -> bool:
        if page.is_closed():
            return False
        try:
            return bool(await page.evaluate(HUD_SCRIPT, {"status": status, "message": message}))
        except Exception as exc:
            LOG.debug("Falha ao atualizar HUD no Chrome: %s", exc)
            return False
