import json
import tempfile
import unittest
from pathlib import Path

from achilles.cli.app import build_parser
from achilles.services.application import ApplicationServices
from achilles.services.errors import ServiceError
from achilles.services.named_sessions import NamedSessionRegistry
from achilles.services.policy import PolicyEngine
from achilles.services.workflow_engine import WorkflowEngine, load_workflow


class NamedSessionTests(unittest.TestCase):
    def test_registry_lifecycle_and_profile_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            registry = NamedSessionRegistry(Path(root))
            created = registry.create("work", port=19222)
            self.assertEqual(created["cdp_port"], 19222)
            self.assertEqual(registry.get()["name"], "work")
            self.assertTrue(Path(created["profile_dir"]).is_dir())
            self.assertEqual(registry.use("work")["name"], "work")
            removed = registry.remove("work")
            self.assertTrue(removed["profile_preserved"])
            self.assertTrue(Path(created["profile_dir"]).is_dir())

    def test_invalid_session_name(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ServiceError):
                NamedSessionRegistry(Path(root)).create("../../unsafe", port=19223)


class PolicyTests(unittest.TestCase):
    def test_read_only_and_domain_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            policy_path = Path(root) / "policy.yaml"
            policy_path.write_text(
                "read_only: true\ndomains:\n  allow: ['*.example.com']\n",
                encoding="utf-8",
            )
            policy = PolicyEngine(policy_path)
            policy.check("browser_read_content", {}, "https://docs.example.com/path")
            with self.assertRaises(ServiceError):
                policy.check("browser_navigate", {"url": "https://docs.example.com"})
            with self.assertRaises(ServiceError):
                policy.check("browser_read_content", {}, "https://evil.test")


class FakeServices:
    def __init__(self) -> None:
        self.calls = []

    async def call(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "browser_extract":
            return {"items": [{"name": "A"}], "count": 1}
        return {"status": "ok"}


class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_workflow_checkpoint_and_export(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "flow.yaml"
            source.write_text(
                "name: smoke\nsteps:\n  - navigate: https://example.test\n"
                "  - extract:\n      items_selector: '.row'\n"
                "      fields:\n        name:\n          selector: '.name'\n"
                f"  - export:\n      path: '{Path(root) / 'items.jsonl'}'\n",
                encoding="utf-8",
            )
            workflow = load_workflow(str(source))
            fake = FakeServices()
            engine = WorkflowEngine(fake)
            engine.root = Path(root) / "runs"
            engine.root.mkdir()
            result = await engine.execute(workflow, "smoke")
            self.assertEqual(result["status"], "completed")
            self.assertEqual(fake.calls[0][0], "browser_navigate")
            exported = json.loads((Path(root) / "items.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(exported["name"], "A")


class PlatformContractTests(unittest.TestCase):
    def test_new_tools_and_cli_commands_are_discoverable(self) -> None:
        names = {tool["name"] for tool in ApplicationServices.tools()["tools"]}
        self.assertTrue({
            "browser_find_and_act",
            "browser_fill_form",
            "browser_extract_paginated",
            "browser_screenshot",
            "browser_upload",
            "browser_download",
            "browser_events",
            "browser_recording",
        }.issubset(names))
        parser = build_parser()
        self.assertEqual(parser.parse_args(["session", "create", "work"]).session_operation, "create")
        self.assertEqual(parser.parse_args(["run", "flow.yaml"]).command, "run")
        self.assertEqual(parser.parse_args(["mission", "collect data"]).command, "mission")
        self.assertEqual(parser.parse_args(["setup", "--client", "cursor"]).client, "cursor")


class RecordingTests(unittest.IsolatedAsyncioTestCase):
    async def test_recording_omits_form_values(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            destination = Path(root) / "recorded.yaml"
            app = ApplicationServices(19999)
            try:
                await app.call("browser_recording", {"operation": "start"})
                app._record_step(
                    "browser_fill_form",
                    {"fields": {"Email": "private@example.test"}},
                )
                result = await app.call(
                    "browser_recording",
                    {"operation": "stop", "output_path": str(destination)},
                )
                self.assertEqual(result["steps"], 1)
                content = destination.read_text(encoding="utf-8")
                self.assertNotIn("private@example.test", content)
                self.assertIn("${EMAIL}", content)
            finally:
                await app.close()


if __name__ == "__main__":
    unittest.main()
