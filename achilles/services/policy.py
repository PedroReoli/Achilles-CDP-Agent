"""Políticas locais de domínio e ferramenta aplicadas antes da execução."""

import fnmatch
import ipaddress
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

import yaml

from .errors import ServiceError
from .named_sessions import achilles_data_dir

MUTATING_TOOLS = {
    "browser_select_page",
    "browser_new_tab",
    "browser_close_tab",
    "browser_navigate",
    "browser_scroll",
    "browser_action",
    "browser_find_and_act",
    "browser_fill_form",
    "browser_upload",
    "browser_download",
    "browser_handle_dialog",
    "browser_recording",
    "browser_bookmarks_create",
    "browser_bookmarks_update",
    "browser_bookmarks_remove",
    "app_launch",
    "app_attach",
    "app_action",
    "app_find_and_act",
    "app_fill_form",
    "app_click_at",
    "app_close",
    "qa_request",
    "qa_run_suite",
}

DEFAULT_PROTECTED_APPS = [
    "consent.exe",
    "credentialuibroker.exe",
    "lsass.exe",
    "logonui.exe",
    "winlogon.exe",
]


class PolicyEngine:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or achilles_data_dir() / "policy.yaml"
        self.config = self._load()

    def _load(self) -> Dict[str, Any]:
        if not self.path.is_file():
            return {}
        try:
            value = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            raise ServiceError("POLICY_INVALID", "Arquivo policy.yaml inválido.") from exc
        if not isinstance(value, dict):
            raise ServiceError("POLICY_INVALID", "A política precisa ser um objeto YAML.")
        return value

    @staticmethod
    def _matches(host: str, patterns: list[str]) -> bool:
        return any(fnmatch.fnmatch(host.casefold(), pattern.casefold()) for pattern in patterns)

    def check(self, tool: str, arguments: Dict[str, Any], current_url: str = "") -> None:
        denied = self.config.get("tools", {}).get("deny", [])
        if tool in denied:
            raise ServiceError("POLICY_DENIED", f"A política bloqueia a ferramenta {tool}.")
        if self.config.get("read_only") and tool in MUTATING_TOOLS:
            raise ServiceError("POLICY_DENIED", "A política está em modo somente leitura.")
        candidate = arguments.get("url") or current_url
        host = (urlsplit(candidate).hostname or "").casefold()
        if not host:
            return
        domains = self.config.get("domains", {})
        denied_domains = domains.get("deny", [])
        allowed_domains = domains.get("allow", [])
        if self._matches(host, denied_domains):
            raise ServiceError("DOMAIN_DENIED", f"A política bloqueia o domínio {host}.")
        if allowed_domains and not self._matches(host, allowed_domains):
            raise ServiceError("DOMAIN_DENIED", f"O domínio {host} não está na allowlist.")

    def check_desktop(self, tool: str, executable: str, title: str) -> None:
        """Aplica política ao alvo real depois que PID/handle foram resolvidos."""
        desktop = self.config.get("desktop", {})
        if not isinstance(desktop, dict):
            raise ServiceError("POLICY_INVALID", "desktop precisa ser um objeto YAML.")
        if desktop.get("read_only") and tool in MUTATING_TOOLS:
            raise ServiceError("POLICY_DENIED", "A política de desktop está em modo somente leitura.")
        if tool == "app_click_at" and desktop.get("allow_coordinate_actions", True) is False:
            raise ServiceError("POLICY_DENIED", "A política bloqueia ações por coordenada.")
        if tool == "app_launch" and desktop.get("allow_launch", True) is False:
            raise ServiceError("POLICY_DENIED", "A política bloqueia abertura de aplicativos.")
        if tool == "app_close" and desktop.get("allow_close", True) is False:
            raise ServiceError("POLICY_DENIED", "A política bloqueia fechamento de janelas.")
        candidate = executable.casefold()
        basename = Path(candidate).name
        denied = desktop.get("deny_apps", DEFAULT_PROTECTED_APPS)
        allowed = desktop.get("allow_apps", [])
        if not isinstance(denied, list) or not isinstance(allowed, list):
            raise ServiceError("POLICY_INVALID", "allow_apps e deny_apps precisam ser listas.")
        if self._matches(candidate, denied) or self._matches(basename, denied):
            raise ServiceError("APP_DENIED", f"A política bloqueia o aplicativo {basename}.")
        if allowed and not (self._matches(candidate, allowed) or self._matches(basename, allowed)):
            raise ServiceError("APP_DENIED", f"O aplicativo {basename} não está na allowlist.")
        denied_titles = desktop.get("deny_window_titles", [])
        if denied_titles and self._matches(title, denied_titles):
            raise ServiceError("APP_DENIED", "A política bloqueia esta janela.")

    def check_qa(self, url: str, method: str, allow_mutating: bool = False) -> None:
        """Limita QA HTTP ao escopo autorizado e impede mutações implícitas."""
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ServiceError("QA_TARGET_INVALID", "QA aceita somente URLs HTTP(S) completas.")
        if parsed.username or parsed.password:
            raise ServiceError("QA_TARGET_INVALID", "Credenciais não podem ser incluídas na URL.")
        host = parsed.hostname.casefold()
        qa = self.config.get("qa", {})
        if not isinstance(qa, dict):
            raise ServiceError("POLICY_INVALID", "qa precisa ser um objeto YAML.")
        denied = qa.get("deny_hosts", [])
        allowed = qa.get("allow_hosts", ["localhost", "127.0.0.1", "::1"])
        if not isinstance(denied, list) or not isinstance(allowed, list):
            raise ServiceError("POLICY_INVALID", "qa.allow_hosts e qa.deny_hosts precisam ser listas.")
        if self._matches(host, denied):
            raise ServiceError("QA_SCOPE_DENIED", f"O escopo QA bloqueia {host}.")
        if not self._matches(host, allowed):
            raise ServiceError(
                "QA_SCOPE_DENIED",
                f"{host} não está em qa.allow_hosts do policy.yaml.",
            )
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address and (address.is_link_local or address.is_multicast or address.is_unspecified):
            raise ServiceError("QA_SCOPE_DENIED", "Endereço especial não pode ser alvo de QA.")
        if address and address.is_private and not address.is_loopback:
            if qa.get("allow_private_networks", False) is not True:
                raise ServiceError(
                    "QA_SCOPE_DENIED",
                    "Rede privada exige qa.allow_private_networks: true.",
                )
        normalized_method = method.upper()
        if normalized_method not in ("GET", "HEAD", "OPTIONS"):
            if not allow_mutating or qa.get("allow_mutating_methods", False) is not True:
                raise ServiceError(
                    "QA_MUTATION_DENIED",
                    "Método mutável exige allow_mutating e qa.allow_mutating_methods: true.",
                )
