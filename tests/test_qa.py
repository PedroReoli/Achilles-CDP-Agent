import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from achilles.cli.app import build_parser
from achilles.services.application import ApplicationServices, resolve_toolsets
from achilles.services.errors import ServiceError
from achilles.services.policy import PolicyEngine
from achilles.services.qa_contracts import QaCase, QaSuite
from achilles.services.qa_engine import QaEngine, _redact_html_tokens
from achilles.services.qa_service import QaService
from achilles.services.traffic_journal import TrafficJournal
from achilles.studio.server import create_studio_app


class FixtureHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def _send(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/health"):
            self._send(200, {"status": "ok", "version": 1})
        else:
            self._send(404, {"error": "not_found"})

    def do_POST(self):
        length = int(self.headers.get("content-length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        self._send(201, {"received": payload})


class QaRuntimeTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        policy_path = self.root / "policy.yaml"
        policy_path.write_text(
            "qa:\n  allow_hosts: [127.0.0.1]\n  allow_mutating_methods: true\n",
            encoding="utf-8",
        )
        self.engine = QaEngine(PolicyEngine(policy_path))
        self.engine.runs_root = self.root / "runs"
        self.engine.runs_root.mkdir()
        self.base = f"http://127.0.0.1:{self.port}"

    async def asyncTearDown(self):
        await self.engine.close()
        self.temp.cleanup()

    async def test_request_assertions_suite_and_reports(self):
        case = QaCase(
            id="health",
            name="health",
            method="GET",
            url=self.base + "/health",
            expected_status=[200],
            assertions=[
                {"kind": "json_path_equals", "key": "status", "expected": "ok"},
                {"kind": "schema_required", "expected": ["status", "version"]},
                {"kind": "response_time_ms", "expected": 3000},
            ],
        )
        result = await self.engine.execute_case(case)
        self.assertEqual(result["status"], "passed")
        suite = QaSuite(
            name="fixture",
            base_url=self.base,
            cases=[
                {"name": "health", "path": "/health", "expected_status": [200]},
                {
                    "name": "echo",
                    "method": "POST",
                    "path": "/echo",
                    "json_body": {"hello": "world"},
                    "expected_status": [201],
                    "allow_mutating": True,
                },
            ],
        )
        report = await self.engine.run_suite(suite)
        self.assertEqual(report["summary"]["passed"], 2)
        html = self.engine.export_report(report, "html", None)
        junit = self.engine.export_report(report, "junit", None)
        self.assertTrue(Path(html["path"]).is_file())
        self.assertIn("<testsuite", junit["content"])
        self.assertEqual(self.engine.load_run(report["run_id"])["suite"], "fixture")

    async def test_openapi_discovery_and_plan_guard_mutations(self):
        spec = {
            "openapi": "3.1.0",
            "servers": [{"url": self.base}],
            "paths": {
                "/health": {"get": {"summary": "Health", "responses": {"200": {}}}},
                "/users": {"post": {"summary": "Create user", "responses": {"201": {}}}},
            },
        }
        source = self.root / "openapi.json"
        source.write_text(json.dumps(spec), encoding="utf-8")
        loaded = await self.engine.load_openapi(str(source))
        endpoints = self.engine.discover_openapi(loaded)
        plan = self.engine.generate_plan(endpoints, "generated", self.base, False)
        self.assertEqual(len(endpoints), 2)
        self.assertEqual(len(plan["suite"]["cases"]), 1)
        self.assertEqual(plan["suite"]["cases"][0]["expected_status"], [200])
        self.assertEqual(plan["skipped"][0]["reason"], "mutating_manual_review")

    async def test_defensive_security_audit_reports_explicit_coverage(self):
        service = QaService(TrafficJournal(), self.engine.policy)
        await service.engine.close()
        service.engine = self.engine
        result = await service.call(
            "qa_security_audit",
            {"urls": [self.base + "/health"], "include_traffic": False, "timeout_ms": 5000},
        )
        rules = {item["rule_id"] for item in result["findings"]}
        self.assertIn("CORS_WILDCARD", rules)
        self.assertIn("authorization_exploitation", result["not_tested"])


class QaPolicyAndCatalogTests(unittest.TestCase):
    def test_html_evidence_redacts_csrf_meta_tokens(self):
        source = '<meta name="achilles-token" content="private-random-token">'
        redacted = _redact_html_tokens(source)
        self.assertNotIn("private-random-token", redacted)
        self.assertIn("[REDACTED]", redacted)

    def test_scope_and_mutation_are_deny_by_default(self):
        with tempfile.TemporaryDirectory() as root:
            policy = PolicyEngine(Path(root) / "missing.yaml")
            policy.check_qa("http://127.0.0.1:8000/health", "GET")
            with self.assertRaises(ServiceError):
                policy.check_qa("https://example.com", "GET")
            with self.assertRaises(ServiceError):
                policy.check_qa("http://127.0.0.1:8000/users", "POST", True)

    def test_toolset_cli_and_studio_are_discoverable(self):
        names = {tool["name"] for tool in ApplicationServices.tools(resolve_toolsets("qa"))["tools"]}
        self.assertEqual(
            names,
            {"qa_status", "qa_discover", "qa_plan", "qa_request", "qa_run_suite", "qa_report", "qa_security_audit", "qa_runs"},
        )
        parser = build_parser()
        self.assertEqual(parser.parse_args(["studio", "--no-open"]).command, "studio")
        request = parser.parse_args(["qa", "request", "http://127.0.0.1:8000/health"])
        self.assertEqual(request.qa_operation, "request")

    def test_studio_serves_assets_and_protects_api(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(
            os.environ, {"ACHILLES_DATA_DIR": root}, clear=False
        ):
            services = ApplicationServices(19999)
            app = create_studio_app(services=services, studio_token="test-token")
            with TestClient(
                app,
                base_url="http://127.0.0.1",
                client=("127.0.0.1", 50000),
            ) as client:
                page = client.get("/")
                self.assertEqual(page.status_code, 200)
                self.assertIn("Achilles QA Studio", page.text)
                self.assertEqual(client.get("/api/status").status_code, 401)
                response = client.get(
                    "/api/status", headers={"X-Achilles-Studio-Token": "test-token"}
                )
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.json()["studio"])


if __name__ == "__main__":
    unittest.main()
