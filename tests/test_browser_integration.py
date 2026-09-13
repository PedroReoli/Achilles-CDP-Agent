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
