"""Gera configuração MCP determinística sem editar clientes silenciosamente."""

import json
import os
import shutil
from pathlib import Path
from typing import Optional


def executable_path() -> str:
    suffix = ".exe" if os.name == "nt" else ""
    canonical = Path(os.environ.get("UV_TOOL_BIN_DIR", Path.home() / ".local" / "bin")) / f"achilles{suffix}"
    if canonical.is_file():
        return str(canonical.resolve())
    discovered = shutil.which("achilles")
    if discovered:
        return str(Path(discovered).resolve())
    return str(canonical.resolve())


def run_setup(client: str, output: Optional[str], tools: str) -> None:
    server = {
        "command": executable_path(),
        "args": ["mcp", "--tools", tools],
    }
    if client in ("claude", "cursor", "generic"):
        payload = {"mcpServers": {"achilles": server}}
    else:
        raise ValueError("Cliente MCP desconhecido.")
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if output:
        destination = Path(output).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise FileExistsError("O arquivo já existe; escolha outro caminho.")
        destination.write_text(rendered, encoding="utf-8")
        print(json.dumps({"ok": True, "path": str(destination), "config": payload}, ensure_ascii=False))
    else:
        print(rendered, end="")
