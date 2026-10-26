import os
import signal
import sys
import tempfile
import unittest
from pathlib import Path

from achilles.mcp.server import tool_content
from achilles.services.application import ApplicationServices, resolve_toolsets
from achilles.services.desktop_service import DesktopService
from achilles.services.errors import ServiceError
from achilles.services.policy import PolicyEngine


class FakeDesktopBackend:
    def status(self):
        return {"supported": True, "backend": "fake", "platform": "windows"}

    def list_apps(self, visible_only=True, limit=100):
        return {"apps": [{"app_id": "app-1"}], "count": 1, "truncated": False}


class DesktopContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_desktop_service_serializes_backend_calls(self) -> None:
        service = DesktopService(backend=FakeDesktopBackend())
        try:
            status = await service.call("app_status", {})
            apps = await service.call("app_list", {"visible_only": True, "limit": 10})
        finally:
            await service.close()
        self.assertEqual(status["backend"], "fake")
        self.assertEqual(apps["apps"][0]["app_id"], "app-1")

    def test_catalog_exposes_desktop_toolset_and_annotations(self) -> None:
        tools = {
            item["name"]: item
            for item in ApplicationServices.tools(resolve_toolsets("desktop"))["tools"]
        }
        self.assertIn("app_snapshot", tools)
        self.assertIn("app_fill_form", tools)
        self.assertIn("app_click_at", tools)
        self.assertTrue(tools["app_snapshot"]["annotations"]["readOnlyHint"])
        self.assertTrue(tools["app_click_at"]["annotations"]["destructiveHint"])
        self.assertFalse(tools["app_click_at"]["annotations"]["idempotentHint"])

    def test_mcp_embeds_small_desktop_screenshot(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            image = Path(root) / "window.png"
            image.write_bytes(b"synthetic-png")
            content = tool_content("app_screenshot", {"path": str(image)}, {"path": str(image)})
        self.assertEqual(content[1]["type"], "image")
        self.assertEqual(content[1]["mimeType"], "image/png")

    def test_launch_contract_accepts_executable_aumid_or_uri(self) -> None:
        tools = {
            item["name"]: item for item in ApplicationServices.tools()["tools"]
        }
        schema = tools["app_launch"]["inputSchema"]
        self.assertIn("app_user_model_id", schema["properties"])
        self.assertIn("uri", schema["properties"])

    @unittest.skipUnless(sys.platform == "win32", "Windows worker only")
    async def test_worker_restarts_after_isolated_process_stops(self) -> None:
        service = DesktopService()
        try:
            first = await service.call("app_status", {})
            process = service.process
            self.assertIsNotNone(process)
            process.terminate()
            await process.wait()
            second = await service.call("app_status", {})
        finally:
            await service.close()
        self.assertNotEqual(first["worker_pid"], second["worker_pid"])


class DesktopPolicyTests(unittest.TestCase):
    def test_allowlist_and_coordinate_policy_use_resolved_executable(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "policy.yaml"
            source.write_text(
                "desktop:\n"
                "  allow_apps: ['notepad.exe']\n"
                "  allow_coordinate_actions: false\n",
                encoding="utf-8",
            )
            policy = PolicyEngine(source)
            policy.check_desktop("app_snapshot", r"C:\\Windows\\notepad.exe", "Untitled")
            with self.assertRaises(ServiceError):
                policy.check_desktop("app_snapshot", r"C:\\Windows\\calc.exe", "Calculator")
            with self.assertRaises(ServiceError):
                policy.check_desktop("app_click_at", r"C:\\Windows\\notepad.exe", "Untitled")

    def test_secure_desktop_processes_are_denied_by_default(self) -> None:
        policy = PolicyEngine(Path("missing-policy-for-test.yaml"))
        with self.assertRaises(ServiceError):
            policy.check_desktop("app_attach", r"C:\\Windows\\System32\\consent.exe", "UAC")


@unittest.skipUnless(
    sys.platform == "win32" and os.environ.get("ACHILLES_DESKTOP_TESTS") == "1",
    "Set ACHILLES_DESKTOP_TESTS=1 for isolated Windows UIA tests",
)
class DesktopIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.previous_data_dir = os.environ.get("ACHILLES_DATA_DIR")
        self.temporary_data = tempfile.TemporaryDirectory()
        os.environ["ACHILLES_DATA_DIR"] = self.temporary_data.name

    async def asyncTearDown(self) -> None:
        if self.previous_data_dir is None:
            os.environ.pop("ACHILLES_DATA_DIR", None)
        else:
            os.environ["ACHILLES_DATA_DIR"] = self.previous_data_dir
        self.temporary_data.cleanup()

    async def test_launch_snapshot_visual_click_and_semantic_close(self) -> None:
        script = (
            "Add-Type -AssemblyName System.Windows.Forms;"
            "$form=New-Object System.Windows.Forms.Form;"
            "$form.Text='Achilles Desktop Integration';$form.Width=420;$form.Height=340;"
            "$label=New-Object System.Windows.Forms.Label;"
            "$label.Text='Initial State';$label.Left=130;$label.Top=25;$label.Width=180;"
            "$emailBox=New-Object System.Windows.Forms.TextBox;"
            "$emailBox.AccessibleName='Email';$emailBox.Left=110;$emailBox.Top=60;"
            "$emailBox.Width=190;"
            "$activate=New-Object System.Windows.Forms.Button;"
            "$activate.Text='Activate Achilles Test';$activate.Left=110;$activate.Top=105;"
            "$activate.Width=190;$activate.Add_Click({$label.Text='Activated State'});"
            "$submit=New-Object System.Windows.Forms.Button;"
            "$submit.Text='Submit Achilles Test';$submit.Left=110;$submit.Top=155;$submit.Width=190;"
            "$submit.Add_Click({$label.Text=('Submitted '+$emailBox.Text)});"
            "$close=New-Object System.Windows.Forms.Button;"
            "$close.Text='Close Achilles Test';$close.Left=110;$close.Top=205;$close.Width=190;"
            "$close.Add_Click({$form.Close()});"
            "$form.Controls.AddRange(@($label,$emailBox,$activate,$submit,$close));"
            "[void]$form.ShowDialog()"
        )
        app = ApplicationServices(19998)
        process_id = None
        try:
            status = await app.call("app_status", {})
            self.assertNotEqual(status["worker_pid"], os.getpid())
            launched = await app.call(
                "app_launch",
                {
                    "executable": "powershell.exe",
                    "arguments": ["-NoProfile", "-STA", "-WindowStyle", "Hidden", "-Command", script],
                    "window_title": "Achilles Desktop Integration",
                    "timeout_ms": 15000,
                },
            )
            process_id = launched["process_id"]
            filled = await app.call(
                "app_fill_form",
                {
                    "process_id": process_id,
                    "fields": {"Email": "agent@example.test"},
                    "submit_query": "Submit Achilles Test",
                },
            )
            self.assertTrue(filled["submitted"])
            await app.call(
                "app_wait_for_state",
                {
                    "process_id": process_id,
                    "query": "Submitted agent@example.test",
                    "timeout_ms": 5000,
                },
            )
            snapshot = await app.call("app_snapshot", {"process_id": process_id, "limit": 100})
            names = [item["name"] for item in snapshot["elements"]]
            self.assertIn("Activate Achilles Test", names, names)
            button = next(
                item for item in snapshot["elements"] if item["name"] == "Activate Achilles Test"
            )
            screenshot = await app.call("app_screenshot", {"process_id": process_id})
            window = screenshot["window"]["bounds"]
            bounds = button["bounds"]
            clicked = await app.call(
                "app_click_at",
                {
                    "screenshot_id": screenshot["screenshot_id"],
                    "x": (bounds["left"] + bounds["right"]) // 2 - window["left"],
                    "y": (bounds["top"] + bounds["bottom"]) // 2 - window["top"],
                },
            )
            self.assertEqual(clicked["status"], "ok")
            reached = await app.call(
                "app_wait_for_state",
                {"process_id": process_id, "query": "Activated State", "timeout_ms": 5000},
            )
            self.assertEqual(reached["status"], "reached")
            closed = await app.call(
                "app_find_and_act",
                {
                    "process_id": process_id,
                    "query": "Close Achilles Test",
                    "action": "click",
                },
            )
            self.assertEqual(closed["mode"], "semantic")
        finally:
            await app.close()
            if process_id:
                try:
                    os.kill(process_id, signal.SIGTERM)
                except OSError:
                    pass


if __name__ == "__main__":
    unittest.main()
