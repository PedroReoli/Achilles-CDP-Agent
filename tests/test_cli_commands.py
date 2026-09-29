"""
test_cli_commands.py — Testes unitários para comandos CLI e interface do Achilles.
"""
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from achilles.cli import commands
from achilles.cli.app import build_parser, main
from achilles.cli.extension import prepare_extension
from achilles.cli.i18n import I18n


class TestCliCommands(unittest.IsolatedAsyncioTestCase):
    def test_command_functions_exist(self):
        """Verifica se todas as funções esperadas pelo app.py e pelo protocolo existem."""
        expected_functions = [
            "run_status",
            "run_act",
            "run_curl",
            "run_open",
            "run_pages",
            "run_snapshot",
            "run_read",
            "run_report",
            "run_traffic",
            "run_audit",
            "run_wait_challenge",
            "run_domain_memory",
            "run_export_report",
            "run_protocol",
            "run_interactive",
            "ensure_chrome_running",
        ]
        for fn_name in expected_functions:
            self.assertTrue(
                hasattr(commands, fn_name),
                f"Função '{fn_name}' não encontrada em achilles.cli.commands"
            )

    def test_cli_parser_act_commands(self):
        """Verifica se o parser aceita as ações incluindo scroll."""
        parser = build_parser()
        
        # Test click
        args = parser.parse_args(["act", "click", "ref_1"])
        self.assertEqual(args.command, "act")
        self.assertEqual(args.action, "click")
        self.assertEqual(args.element_ref, "ref_1")
        
        # Test fill with value
        args = parser.parse_args(["act", "fill", "ref_2", "hello world"])
        self.assertEqual(args.action, "fill")
        self.assertEqual(args.value, "hello world")
        
        # Test scroll
        args = parser.parse_args(["act", "scroll", "down", "500"])
        self.assertEqual(args.action, "scroll")
        self.assertEqual(args.element_ref, "down")
        self.assertEqual(args.value, "500")

    def test_cli_parser_status_and_curl(self):
        """Verifica se o parser aceita status e curl."""
        parser = build_parser()
        args_status = parser.parse_args(["status", "--cdp-port", "9222"])
        self.assertEqual(args_status.command, "status")
        self.assertEqual(args_status.cdp_port, 9222)

        args_curl = parser.parse_args(["curl", "req_123", "--shell", "powershell"])
        self.assertEqual(args_curl.command, "curl")
        self.assertEqual(args_curl.request_id, "req_123")
        self.assertEqual(args_curl.shell, "powershell")

    def test_extension_command_prepares_browser_files(self):
        self.assertTrue(build_parser().parse_args(["--extension"]).extension)
        with tempfile.TemporaryDirectory() as root:
            folder, archive = prepare_extension(Path(root))
            self.assertEqual(sorted(item.name for item in folder.iterdir()),
                             ["bridge.html", "manifest.json"])
            with zipfile.ZipFile(archive) as bundle:
                self.assertEqual(sorted(bundle.namelist()), ["bridge.html", "manifest.json"])
                self.assertEqual(bundle.read("manifest.json"), (folder / "manifest.json").read_bytes())
            with patch("achilles.cli.extension.run_extension_package") as package:
                main(["--extension"])
                package.assert_called_once_with()

    @patch("achilles.cli.commands.ensure_chrome_running")
    async def test_run_status_mocked(self, mock_ensure):
        """Testa execução de run_status com services mockado."""
        mock_services = MagicMock()
        mock_services.call = AsyncMock(return_value={
            "cdp_url": "http://127.0.0.1:9222",
            "mode": "attach",
            "recorded_requests": 5,
            "generation": 1,
        })
        mock_services.close = AsyncMock()
        
        await commands.run_status(9222, I18n("pt"), services=mock_services)
        mock_services.call.assert_awaited_once_with("browser_status", {})

    @patch("achilles.cli.commands.ensure_chrome_running")
    async def test_run_act_mocked(self, mock_ensure):
        """Testa execução de run_act com services mockado."""
        mock_services = MagicMock()
        mock_services.call = AsyncMock(side_effect=[
            # browser_snapshot
            {"snapshot_id": "snap_1", "page_id": "p1"},
            # browser_action
            {"duration_ms": 12, "action": "click"},
        ])
        mock_services.close = AsyncMock()
        
        await commands.run_act(9222, "click", "[@frame_1/btn_1]", page_id="p1", i18n=I18n("pt"), services=mock_services)
        self.assertEqual(mock_services.call.await_count, 2)


if __name__ == "__main__":
    unittest.main()
