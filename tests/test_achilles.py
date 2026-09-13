"""
test_achilles.py — Suíte de testes unitários do Achilles CDP Agent.
"""
import unittest
from achilles.core.dom_parser import DOMSemanticParser
from achilles.core.network_recorder import NetworkRecorder
from achilles.security.auditor import SecurityAuditor
from achilles.reverse_api.openapi import OpenAPIGenerator
from achilles.testing.playwright_exporter import PlaywrightTestExporter


class TestAchilles(unittest.TestCase):
    def test_dom_formatter(self):
        sample = [
            {"id": 1, "tag": "button", "type": "", "text": "Entrar", "disabled": False},
            {"id": 2, "tag": "input", "type": "email", "text": "seu@email.com", "disabled": False}
        ]
        formatted = DOMSemanticParser.format_tree_for_llm(sample)
        self.assertTrue("[#1] <button>" in formatted)
        self.assertTrue("Entrar" in formatted)
        self.assertTrue("[#2] <input:email>" in formatted)

    def test_network_recorder_curl(self):
        recorder = NetworkRecorder()
        recorder.record({
            "url": "https://api.test.com/v1/auth",
            "method": "POST",
            "headers": {"Content-Type": "application/json"},
            "post_data": '{"user":"pedro"}',
            "resource_type": "xhr"
        })
        self.assertEqual(len(recorder.requests), 1)
        self.assertTrue("curl -X POST 'https://api.test.com/v1/auth'" in recorder.requests[0]["curl"])

    def test_security_auditor_jwt_and_service_role(self):
        token_none = "eyJhbGciOiJub25lIn0.eyJzdWIiOiIxMjMiLCJyb2xlIjoic2VydmljZV9yb2xlIn0."
        res = SecurityAuditor.inspect_jwt(token_none)
        self.assertTrue(res["valid"])
        self.assertTrue(any("service_role" in issue for issue in res["issues"]))
        self.assertTrue(any("none" in issue for issue in res["issues"]))

    def test_openapi_generator(self):
        reqs = [
            {"url": "https://api.app.com/items/9981", "method": "GET", "headers": {}, "post_data": None}
        ]
        spec = OpenAPIGenerator.generate_spec(reqs, title="App Test")
        self.assertEqual(spec["openapi"], "3.0.0")
        self.assertIn("/items/{id}", spec["paths"])

    def test_playwright_exporter(self):
        script = PlaywrightTestExporter.generate_python("https://app.com", [{"url": "https://app.com/api", "method": "GET"}])
        self.assertIn("async def test_achilles_flow():", script)


if __name__ == "__main__":
    unittest.main()
