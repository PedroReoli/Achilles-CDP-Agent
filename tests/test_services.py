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
            await app.call("browser_navigate", {"url": ""})
        with self.assertRaises(ServiceError):
            await app.call("browser_scroll", {"direction": "invalid_dir"})
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
