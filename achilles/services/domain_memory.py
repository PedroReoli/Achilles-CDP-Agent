"""Memória semântica de rotas, atalhos e estado de autenticação por domínio."""

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

LOG = logging.getLogger(__name__)


def get_memory_file_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Achilles"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "Achilles"
    else:
        base = Path.home() / ".config" / "achilles"
    base.mkdir(parents=True, exist_ok=True)
    return base / "domain_memory.json"


class DomainMemoryEngine:
    def __init__(self, file_path: Optional[Path] = None) -> None:
        self.file_path = file_path or get_memory_file_path()
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self.file_path.exists():
            try:
                self._cache = json.loads(self.file_path.read_text(encoding="utf-8"))
            except Exception as exc:
                LOG.warning("Erro ao carregar memória de domínios: %s", exc)
                self._cache = {}
        else:
            self._cache = {}

    def _save(self) -> None:
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            self.file_path.write_text(json.dumps(self._cache, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            LOG.error("Erro ao salvar memória de domínios: %s", exc)

    @staticmethod
    def extract_domain(url_or_domain: str) -> str:
        if "://" in url_or_domain:
            host = urlsplit(url_or_domain).hostname or url_or_domain
        else:
            host = url_or_domain.split("/", 1)[0].split(":", 1)[0]
        return host.lower()

    def get(self, url_or_domain: str) -> Dict[str, Any]:
        domain = self.extract_domain(url_or_domain)
        entry = self._cache.get(domain)
        if entry is None:
            return {
                "domain": domain,
                "known": False,
                "authenticated": False,
                "shortcuts": {},
                "api_endpoints": [],
                "notes": [],
                "last_visited": None,
            }
        return {"domain": domain, "known": True, **entry}

    def remember(
        self,
        url_or_domain: str,
        authenticated: Optional[bool] = None,
        shortcuts: Optional[Dict[str, str]] = None,
        api_endpoints: Optional[List[str]] = None,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        domain = self.extract_domain(url_or_domain)
        if domain not in self._cache:
            self._cache[domain] = {
                "authenticated": False,
                "shortcuts": {},
                "api_endpoints": [],
                "notes": [],
                "last_visited": time.time(),
            }

        entry = self._cache[domain]
        entry["last_visited"] = time.time()

        if authenticated is not None:
            entry["authenticated"] = authenticated
        if shortcuts:
            entry["shortcuts"].update(shortcuts)
        if api_endpoints:
            existing = set(entry.get("api_endpoints", []))
            for ep in api_endpoints:
                if ep not in existing:
                    entry.setdefault("api_endpoints", []).append(ep)
        if note and note not in entry.setdefault("notes", []):
            entry["notes"].append(note)

        self._save()
        return {"domain": domain, "known": True, **entry}

    def list_all(self) -> List[Dict[str, Any]]:
        return [{"domain": d, **data} for d, data in self._cache.items()]

    def clear(self, url_or_domain: Optional[str] = None) -> bool:
        if url_or_domain:
            domain = self.extract_domain(url_or_domain)
            if domain in self._cache:
                del self._cache[domain]
                self._save()
                return True
            return False
        self._cache.clear()
        self._save()
        return True
