"""
cdp_driver.py — Gerenciador assíncrono e resiliente de conexão Chrome CDP (porta 9222).
"""
import asyncio
from typing import Any, List, Optional

from playwright.async_api import Browser, BrowserContext, Page, async_playwright


class CDPDriver:
    """Gerencia a conexão com o navegador Chrome ativo com suporte a reconexão automática."""
    
    def __init__(self, cdp_url: str = "http://127.0.0.1:9222"):
        self.cdp_url = cdp_url
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.on_request_callbacks: List[Any] = []

    def register_request_callback(self, callback):
        self.on_request_callbacks.append(callback)

    async def connect(self) -> Page:
        if self.page and not self.page.is_closed():
            return self.page

        if not self.playwright:
            self.playwright = await async_playwright().start()

        try:
            self.browser = await self.playwright.chromium.connect_over_cdp(self.cdp_url)
            contexts = self.browser.contexts
            if not contexts:
                raise RuntimeError(f"Nenhum contexto encontrado em {self.cdp_url}")
            
            self.context = contexts[0]
            pages = self.context.pages
            self.page = pages[0] if pages else await self.context.new_page()

            async def handle_request(request):
                try:
                    post_data = request.post_data
                except Exception:
                    post_data = None

                req_info = {
                    "url": request.url,
                    "method": request.method,
                    "headers": request.headers,
                    "post_data": post_data,
                    "resource_type": request.resource_type,
                }
                for cb in self.on_request_callbacks:
                    if asyncio.iscoroutinefunction(cb):
                        await cb(req_info)
                    else:
                        cb(req_info)

            self.page.on("request", handle_request)
            return self.page
        except Exception as e:
            raise RuntimeError(f"Falha ao conectar no Chrome CDP ({self.cdp_url}): {str(e)}")

    async def get_page(self) -> Page:
        return await self.connect()

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
