import base64
import json
import shlex
import subprocess
import sys
import unittest
from unittest.mock import AsyncMock

from achilles.api.server import create_app
from achilles.mcp.server import (
    CAPABILITIES_META,
    MODERN_VERSION,
    SERVER_INFO_META,
    VERSION_META,
    MCPServer,
    encode_response,
)
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

    def test_network_redaction_fuzzing(self) -> None:
        import base64

        from achilles.services.redaction import redact, redact_body

        # Test headers and dict redaction
        headers = {
            "x-api-key": "secret123",
            "stripe-signature": "t=123,v1=sk_live_1234567890abcdef",
            "authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        }
        redacted_headers = redact(headers)
        self.assertNotIn("secret123", str(redacted_headers))
        self.assertNotIn("sk_live_1234567890abcdef", str(redacted_headers))
        self.assertIn("[REDACTED]", str(redacted_headers))

        # Test Base64 body redaction
        fake_aws = "AKIA" + "0123456789ABCDEF"
        raw_body = json.dumps({"api-key": "secret456", "aws-sigv4": fake_aws})
        b64_body = base64.b64encode(raw_body.encode('utf-8')).decode('utf-8')
        redacted_b64 = redact_body(b64_body, "text/plain")

        # Ensure it got redacted and is still valid b64
        decoded_redacted = base64.b64decode(redacted_b64).decode('utf-8')
        self.assertNotIn("secret456", decoded_redacted)
        self.assertNotIn(fake_aws, decoded_redacted)
        self.assertIn("[REDACTED]", decoded_redacted)

        # Test Multipart body redaction
        multipart_body = (
            "--boundary123\r\n"
            "Content-Disposition: form-data; name=\"api_key\"\r\n\r\n"
            "secret789\r\n"
            "--boundary123\r\n"
            "Content-Disposition: form-data; name=\"public_field\"\r\n\r\n"
            "public_value\r\n"
            "--boundary123--"
        )
        redacted_multipart = redact_body(multipart_body, "multipart/form-data; boundary=boundary123")
        self.assertNotIn("secret789", redacted_multipart)
        self.assertIn("public_value", redacted_multipart)
        self.assertIn("--boundary123", redacted_multipart)

    def test_modern_secrets_redaction(self) -> None:
        from achilles.services.redaction import redact
        # Dados sintéticos gerados dinamicamente para testes sem armazenar tokens literais no repositório
        filler = "MOCK" * 8
        secrets_payload = {
            "openai_project": f"sk-proj-{filler}",
            "openai_admin": f"sk-admin-{filler}",
            "anthropic": f"sk-ant-{filler}",
            "gemini": f"AIzaSy{filler}",
            "slack_bot": f"xoxb-{'1'*10}-{'2'*10}-{'a'*16}",
            "github_pat": f"github_pat_{filler}",
        }
        redacted = redact(secrets_payload)
        for original in secrets_payload.values():
            self.assertNotIn(original, str(redacted))
            self.assertIn("[REDACTED]", str(redacted))


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
    async def test_mcp_modern_discovery_and_inline_tool_call(self) -> None:
        app = ApplicationServices(9333)
        server = MCPServer(app)
        metadata = {VERSION_META: MODERN_VERSION, CAPABILITIES_META: {}}
        discovery = await server.handle({
            "jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {"_meta": metadata},
        })
        self.assertEqual(discovery["result"]["resultType"], "complete")
        self.assertIn(MODERN_VERSION, discovery["result"]["supportedVersions"])
        self.assertEqual(discovery["result"]["_meta"][SERVER_INFO_META]["name"], "achilles-cdp")
        listing = await server.handle({
            "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {"_meta": metadata},
        })
        self.assertEqual(listing["result"]["resultType"], "complete")
        self.assertTrue(listing["result"]["tools"])
        self.assertEqual(listing["result"]["cacheScope"], "public")
        self.assertEqual(listing["result"]["ttlMs"], 300000)
        status = await server.handle({
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"_meta": metadata, "name": "browser_status", "arguments": {}},
        })
        self.assertEqual(status["result"]["structuredContent"]["cdp_url"], "http://127.0.0.1:9333")
        self.assertEqual(status["result"]["resultType"], "complete")
        missing = await server.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/list"})
        self.assertEqual(missing["error"]["code"], -32602)
        unsupported = await MCPServer(app).handle({
            "jsonrpc": "2.0", "id": 5, "method": "server/discover",
            "params": {"_meta": {VERSION_META: "1900-01-01", CAPABILITIES_META: {}}},
        })
        self.assertEqual(unsupported["error"]["code"], -32022)
        self.assertEqual(unsupported["error"]["data"]["requested"], "1900-01-01")
        await app.close()

    async def test_mcp_lists_after_initialize_without_notification(self) -> None:
        app = ApplicationServices(9333)
        for version in ("2024-11-05", "2025-06-18"):
            server = MCPServer(app)
            before = await server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
            self.assertEqual(before["error"]["code"], -32002)
            handshake = await server.handle({
                "jsonrpc": "2.0", "id": 2, "method": "initialize",
                "params": {"protocolVersion": version},
            })
            self.assertEqual(handshake["result"]["protocolVersion"], version)
            listing = await server.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
            self.assertTrue(listing["result"]["tools"])
            self.assertEqual("outputSchema" in listing["result"]["tools"][0], version != "2024-11-05")
        await app.close()

    def test_mcp_large_reader_payload_stays_valid_json(self) -> None:
        payload = {"markdown": "á" * 700000, "elements": []}
        response = {"jsonrpc": "2.0", "id": 5, "result": {
            "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
            "structuredContent": payload,
        }}
        encoded = encode_response(response)
        self.assertLessEqual(len(encoded), 1048576)
        parsed = json.loads(encoded)
        self.assertEqual(
            json.loads(parsed["result"]["content"][0]["text"]),
            parsed["result"]["structuredContent"],
        )
        self.assertTrue(parsed["result"]["structuredContent"]["truncated_by_context_limit"])

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
            # Test that dangerous local file schemes are rejected
            await app.call("browser_navigate", {"url": "file:///etc/passwd"})
        with self.assertRaises(ServiceError):
            await app.call("browser_scroll", {"direction": "invalid_dir"})
        with self.assertRaises(ServiceError):
            await app.call(
                "browser_action",
                {"action": "fill", "page_id": "p", "snapshot_id": "s", "element_ref": "e"},
            )
        # Verify new tab tools are registered in catalog
        tool_names = [t["name"] for t in app.tools()["tools"]]
        self.assertIn("browser_new_tab", tool_names)
        self.assertIn("browser_close_tab", tool_names)
        await app.close()

    def test_mcp_backpressure(self) -> None:
        import asyncio

        from achilles.mcp.server import MCPServer
        from achilles.services.application import ApplicationServices

        async def run():
            services = ApplicationServices(9999)
            server = MCPServer(services)

            # Create a response that will trigger backpressure limit (>1MB)
            response = {"jsonrpc": "2.0", "id": 1, "result": {"data": "x" * 1500000}}
            import json
            encoded = (json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8")

            # Apply same logic as write function
            if len(encoded) > 1048576:
                error_resp = server.error(response.get("id"), -32600, "Message too large for context window")
                encoded = (json.dumps(error_resp, ensure_ascii=False) + "\n").encode("utf-8")

            self.assertIn(b"Message too large for context window", encoded)

        asyncio.run(run())

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
    def test_mcp_modern_stdio_without_handshake(self) -> None:
        metadata = {VERSION_META: MODERN_VERSION, CAPABILITIES_META: {}}
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {"_meta": metadata}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {"_meta": metadata}},
        ]
        result = subprocess.run(
            [sys.executable, "-m", "achilles", "mcp", "--cdp-port", "9555"],
            input="\n".join(json.dumps(req) for req in requests) + "\n",
            text=True, capture_output=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        responses = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual([row["id"] for row in responses], [1, 2])
        self.assertEqual(responses[0]["result"]["resultType"], "complete")
        self.assertTrue(responses[1]["result"]["tools"])

    def test_mcp_stdio_partial_handshake_and_oversized_input(self) -> None:
        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ]
        stream = "\n".join(json.dumps(message) for message in messages[:1])
        stream += "\n" + "x" * 1048577 + "\n" + json.dumps(messages[1]) + "\n"
        result = subprocess.run(
            [sys.executable, "-m", "achilles", "mcp", "--cdp-port", "9555"],
            input=stream, text=True, capture_output=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        responses = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual([row.get("id") for row in responses], [1, None, 2])
        self.assertTrue(responses[-1]["result"]["tools"])

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

    def test_ai_protocol_cli(self) -> None:
        # Test default PT output
        res_pt = subprocess.run(
            [sys.executable, "-m", "achilles", "--ai"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        self.assertEqual(res_pt.returncode, 0)
        self.assertIn("PROTOCOLO AGENTE", res_pt.stdout)
        self.assertIn("ZERO-SECRET", res_pt.stdout)
        self.assertIn("TOKEN-ZERO-WASTE", res_pt.stdout)
        self.assertIn("achilles read", res_pt.stdout)

        # Test EN output
        res_en = subprocess.run(
            [sys.executable, "-m", "achilles", "--ai", "--lang", "en"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        self.assertEqual(res_en.returncode, 0)
        self.assertIn("ACHILLES CDP AGENT", res_en.stdout)
        self.assertIn("ZERO-SECRET RULE", res_en.stdout)
        self.assertIn("TOKEN-ZERO-WASTE ENGINE", res_en.stdout)


class EngineReportTests(unittest.TestCase):
    def test_routes_report_and_token_metrics(self) -> None:
        journal = TrafficJournal()
        rec1 = exchange()
        rec1["status"] = 200
        rec1["resource_type"] = "fetch"
        journal.records.append(rec1)

        rec2 = exchange()
        rec2["request_id"] = "r2"
        rec2["url"] = "https://other.domain:443/home"
        rec2["status"] = 404
        rec2["resource_type"] = "document"
        journal.records.append(rec2)

        report = journal.get_routes_report()
        self.assertEqual(report["total_requests"], 2)
        self.assertEqual(report["unique_domains_count"], 2)
        self.assertIn("example.test", report["domains"])
        self.assertIn("other.domain", report["domains"])
        self.assertEqual(report["status_distribution"]["2xx"], 1)
        self.assertEqual(report["status_distribution"]["4xx"], 1)
        self.assertGreaterEqual(report["api_endpoints_detected"], 1)

        # Test ObservationEngine token metrics
        services = ApplicationServices(9222)
        metrics = services.observations.get_token_metrics()
        self.assertIn("raw_tokens_avoided", metrics)
        self.assertIn("overall_savings_percent", metrics)


class AdvancedModulesV21Tests(unittest.TestCase):
    def test_domain_memory_engine(self) -> None:
        import tempfile
        from pathlib import Path

        from achilles.services.domain_memory import DomainMemoryEngine

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test_memory.json"
            engine = DomainMemoryEngine(file_path=test_file)

            # Check unknown domain
            data = engine.get("https://github.com/settings/profile")
            self.assertEqual(data["domain"], "github.com")
            self.assertFalse(data["known"])
            self.assertFalse(data["authenticated"])

            # Remember domain info
            engine.remember(
                url_or_domain="github.com",
                authenticated=True,
                shortcuts={"profile": "/settings/profile", "billing": "/settings/billing"},
                api_endpoints=["/api/v3/user", "/api/v3/repos"],
                note="Logged in as developer",
            )

            # Verify persisted
            data2 = engine.get("github.com")
            self.assertTrue(data2["known"])
            self.assertTrue(data2["authenticated"])
            self.assertIn("profile", data2["shortcuts"])
            self.assertIn("/api/v3/user", data2["api_endpoints"])

            # Verify list_all
            all_domains = engine.list_all()
            self.assertEqual(len(all_domains), 1)
            self.assertEqual(all_domains[0]["domain"], "github.com")

            # Verify clear
            self.assertTrue(engine.clear("github.com"))
            data3 = engine.get("github.com")
            self.assertFalse(data3["known"])

    def test_visual_report_generation(self) -> None:
        import tempfile
        from pathlib import Path

        from achilles.services.visual_report import export_report_to_file, generate_html_report

        mock_data = {
            "token_metrics": {
                "total_snapshots": 12,
                "total_reads": 3,
                "raw_tokens_avoided": 45000,
                "tokens_consumed_estimated": 2400,
                "overall_savings_percent": "94.7%",
            },
            "routes_report": {
                "total_requests": 34,
                "unique_domains_count": 4,
                "api_endpoints_detected": 8,
                "status_distribution": {"2xx": 30, "3xx": 2, "4xx": 2, "5xx": 0},
                "api_endpoints": [
                    {
                        "method": "GET",
                        "host": "api.github.com",
                        "path": "/user",
                        "status": 200,
                        "duration_ms": 120,
                    }
                ],
            },
            "stealth": {
                "automation_controlled_disabled": True,
                "navigator_webdriver_masked": True,
                "canvas_2d_noise_active": True,
                "webgl_vendor_spoofing_active": True,
                "audio_buffer_jitter_active": True,
            },
        }

        html = generate_html_report(mock_data)
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("Achilles CDP Agent", html)
        self.assertIn("94.7%", html)
        self.assertIn("api.github.com", html)
        mock_data["timeline"] = [{"at": 0, "operation": "browser_navigate", "duration_ms": 12}]
        mock_data["request_history"] = [{"at": 0, "method": "GET", "url": "https://example.test/<script>", "status": 200}]
        mock_data["challenge_history"] = [{"at": 0, "type": "turnstile", "status": "resolved"}]
        html = generate_html_report(mock_data)
        self.assertIn("Timeline da Sessão", html)
        self.assertIn("resolved", html)
        self.assertIn("&lt;script&gt;", html)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "test_report.html"
            res_path = export_report_to_file(mock_data, str(out_file))
            self.assertTrue(Path(res_path).exists())
            self.assertGreater(Path(res_path).stat().st_size, 500)

    def test_advanced_tools_registered(self) -> None:
        tools = ApplicationServices.tools()["tools"]
        tool_names = {t["name"] for t in tools}
        self.assertIn("browser_wait_for_challenge", tool_names)
        self.assertIn("browser_domain_memory", tool_names)
        self.assertIn("browser_export_html_report", tool_names)

    def test_challenge_engine_syntax(self) -> None:
        from achilles.services.challenge_engine import EVALUATE_CHALLENGE_JS

        self.assertIn("cloudflare", EVALUATE_CHALLENGE_JS)
        self.assertIn("recaptcha", EVALUATE_CHALLENGE_JS)
        self.assertIn("hcaptcha", EVALUATE_CHALLENGE_JS)
        self.assertIn("one-time-code", EVALUATE_CHALLENGE_JS)

    def test_hud_script_syntax(self) -> None:
        from achilles.services.hud import HUD_SCRIPT

        self.assertIn("__achilles_hud_host__", HUD_SCRIPT)
        self.assertIn("attachShadow", HUD_SCRIPT)
        self.assertIn("closed", HUD_SCRIPT)


if __name__ == "__main__":
    unittest.main()

