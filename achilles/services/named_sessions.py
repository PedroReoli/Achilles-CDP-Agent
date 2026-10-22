"""Registro persistente de sessões nomeadas e portas CDP isoladas."""

import json
import os
import re
import socket
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .errors import ServiceError


def achilles_data_dir() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Achilles"
    else:
        root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "achilles"
    root.mkdir(parents=True, exist_ok=True)
    return root


class NamedSessionRegistry:
    """Mantém nomes, perfis e portas sem depender de um processo daemon."""

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = root or achilles_data_dir()
        self.path = self.root / "sessions.json"
        self.profiles = self.root / "sessions"
        self.profiles.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def validate_name(name: str) -> str:
        normalized = name.strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,47}", normalized):
            raise ServiceError(
                "INVALID_SESSION_NAME",
                "Use 1-48 caracteres: letras minúsculas, números, hífen ou underscore.",
            )
        return normalized

    def _read(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"active": None, "sessions": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data.get("sessions"), dict):
                raise ValueError
            return data
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise ServiceError("SESSION_REGISTRY_INVALID", "Registro de sessões corrompido.") from exc

    def _write(self, data: Dict[str, Any]) -> None:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)

    @staticmethod
    def _port_available(port: int) -> bool:
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return True
            except OSError:
                return False

    def _next_port(self, used: set[int]) -> int:
        for port in range(9222, 9322):
            if port not in used and self._port_available(port):
                return port
        raise ServiceError("NO_CDP_PORT", "Nenhuma porta CDP livre entre 9222 e 9321.")

    def create(self, name: str, port: Optional[int] = None, browser: str = "chrome") -> Dict[str, Any]:
        name = self.validate_name(name)
        if browser not in ("chrome", "edge"):
            raise ServiceError("INVALID_ARGUMENT", "browser deve ser chrome ou edge.")
        data = self._read()
        if name in data["sessions"]:
            raise ServiceError("SESSION_EXISTS", f"A sessão '{name}' já existe.")
        used = {int(item["cdp_port"]) for item in data["sessions"].values()}
        selected_port = port or self._next_port(used)
        if selected_port in used:
            raise ServiceError("PORT_IN_USE", "A porta já pertence a outra sessão Achilles.")
        if port and not self._port_available(selected_port):
            raise ServiceError("PORT_IN_USE", "A porta já está ocupada por outro processo.")
        profile = self.profiles / name / "profile"
        profile.mkdir(parents=True, exist_ok=True)
        now = time.time()
        record = {
            "name": name,
            "cdp_port": selected_port,
            "browser": browser,
            "profile_dir": str(profile),
            "created_at": now,
            "updated_at": now,
        }
        data["sessions"][name] = record
        data["active"] = data.get("active") or name
        self._write(data)
        return record

    def list(self) -> Dict[str, Any]:
        data = self._read()
        sessions = []
        for name, item in sorted(data["sessions"].items()):
            sessions.append({**item, "active": name == data.get("active")})
        return {"active": data.get("active"), "sessions": sessions}

    def get(self, name: Optional[str] = None) -> Dict[str, Any]:
        data = self._read()
        selected = self.validate_name(name) if name else data.get("active")
        if not selected or selected not in data["sessions"]:
            raise ServiceError("SESSION_NOT_FOUND", "Sessão nomeada não encontrada.")
        return data["sessions"][selected]

    def use(self, name: str) -> Dict[str, Any]:
        data = self._read()
        name = self.validate_name(name)
        if name not in data["sessions"]:
            raise ServiceError("SESSION_NOT_FOUND", f"A sessão '{name}' não existe.")
        data["active"] = name
        data["sessions"][name]["updated_at"] = time.time()
        self._write(data)
        return data["sessions"][name]

    def remove(self, name: str) -> Dict[str, Any]:
        data = self._read()
        name = self.validate_name(name)
        if name not in data["sessions"]:
            raise ServiceError("SESSION_NOT_FOUND", f"A sessão '{name}' não existe.")
        record = data["sessions"].pop(name)
        if data.get("active") == name:
            data["active"] = next(iter(data["sessions"]), None)
        self._write(data)
        return {"removed": True, "session": record, "profile_preserved": True}

    def resolve_port(self, name: Optional[str], fallback: int = 9222) -> int:
        if name:
            return int(self.get(name)["cdp_port"])
        env_name = os.environ.get("ACHILLES_SESSION")
        if env_name:
            return int(self.get(env_name)["cdp_port"])
        try:
            return int(self.get()["cdp_port"])
        except ServiceError:
            return fallback
