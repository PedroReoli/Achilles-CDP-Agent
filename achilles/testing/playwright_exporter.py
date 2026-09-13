"""
playwright_exporter.py — Gerador de Scripts de Teste Automatizados E2E.
"""
from typing import List, Dict, Any


class PlaywrightTestExporter:
    @staticmethod
    def generate_python(url: str, requests: List[Dict[str, Any]]) -> str:
        lines = [
            "# test_achilles_e2e.py — Gerado automaticamente pelo Achilles CDP Agent",
            "import pytest",
            "from playwright.async_api import async_playwright",
            "",
            "",
            "@pytest.mark.asyncio",
            "async def test_achilles_flow():",
            "    async with async_playwright() as p:",
            "        browser = await p.chromium.launch(headless=True)",
            "        context = await browser.new_context()",
            "        page = await context.new_page()",
            "",
            f"        # 1. Navegação Inicial",
            f"        await page.goto({repr(url)}, wait_until='networkidle')",
            "        assert page.url != '', 'Página carregada com sucesso'",
            "",
            "        # 2. Asserções de APIs Interceptadas"
        ]

        if not requests:
            lines.append("        pass")
        else:
            for req in requests[:15]:
                method = req.get("method", "GET").upper()
                req_url = req.get("url", "")
                post_data = req.get("post_data")

                if method == "GET":
                    lines.append(f"        res = await page.request.get({repr(req_url)})")
                    lines.append(f"        assert res.status < 400, f'GET falhou com status {{res.status}}'")
                elif method in ["POST", "PUT", "PATCH"]:
                    body_arg = f", data={repr(post_data)}" if post_data else ""
                    lines.append(f"        res = await page.request.{method.lower()}({repr(req_url)}{body_arg})")
                    lines.append(f"        assert res.status < 400, f'{method} falhou com status {{res.status}}'")

        lines.extend(["", "        await browser.close()", ""])
        return "\n".join(lines)
