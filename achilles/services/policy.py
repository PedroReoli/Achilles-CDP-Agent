"""Políticas locais de domínio e ferramenta aplicadas antes da execução."""

import fnmatch
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
}


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
