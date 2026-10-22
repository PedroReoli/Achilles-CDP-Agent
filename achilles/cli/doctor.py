"""Diagnóstico não destrutivo das dependências, do MCP e do endpoint CDP."""

import asyncio
import importlib.metadata
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict

from achilles.mcp.server import MCPServer
from achilles.services.application import ApplicationServices, resolve_toolsets


async def measure_cdp_latency(cdp_port: int) -> float:
    started = time.perf_counter()
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", cdp_port), 1)
        writer.close()
        await writer.wait_closed()
        return (time.perf_counter() - started) * 1000
    except (OSError, asyncio.TimeoutError):
        return -1


def repair_user_path() -> Dict[str, Any]:
    bin_dir = str(Path(os.environ.get("UV_TOOL_BIN_DIR", Path.home() / ".local" / "bin")).resolve())
    if os.name != "nt":
        return {"changed": False, "message": f"Garanta {bin_dir} no PATH do shell."}
    import winreg

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        "Environment",
        0,
        winreg.KEY_READ | winreg.KEY_SET_VALUE,
    ) as key:
        try:
            current, _ = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            current = ""
        entries = [item for item in current.split(";") if item and item.casefold() != bin_dir.casefold()]
        updated = ";".join([bin_dir, *entries])
        changed = updated != current
        if changed:
            winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, updated)
    return {"changed": changed, "path": bin_dir}


async def run_doctor(
    cdp_port: int,
    deep: bool,
    output_json: bool = False,
    fix: bool = False,
) -> bool:
    checks = []
    repairs = []

    def report(status: str, component: str, detail: str) -> None:
        checks.append({"status": status.lower(), "component": component, "detail": detail})
        if not output_json:
            print(f"{status} {component}: {detail}")

    if not output_json:
        print("Achilles CDP Agent — Diagnóstico")
    healthy = sys.version_info >= (3, 11)
    report("OK" if healthy else "FALHA", "Python", f"{sys.version_info.major}.{sys.version_info.minor}")
    executable = shutil.which("achilles")
    if executable:
        report("OK", "PATH", executable)
    else:
        report("FALHA", "PATH", "'achilles' não foi encontrado")
        healthy = False
    if fix:
        try:
            repairs.append({"component": "PATH", **repair_user_path()})
        except (OSError, PermissionError) as exc:
            repairs.append({"component": "PATH", "changed": False, "error": type(exc).__name__})
    for package in ("playwright", "pydantic", "fastapi", "rich"):
        try:
            report("OK", package, importlib.metadata.version(package))
        except importlib.metadata.PackageNotFoundError:
            report("FALHA", package, "dependência ausente")
            healthy = False

    services = ApplicationServices(cdp_port)
    try:
        server = MCPServer(services, resolve_toolsets("core"))
        response = await server.handle({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        })
        tools = await server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        if response and tools and tools.get("result", {}).get("tools"):
            report("OK", "MCP", f"{len(tools['result']['tools'])} ferramentas no toolset core")
        else:
            report("FALHA", "MCP", "handshake ou catálogo indisponível")
            healthy = False
        latency = await measure_cdp_latency(cdp_port)
        if latency < 0:
            report("INFO", "CDP", f"porta {cdp_port} fechada; partida automática na primeira operação")
        else:
            report("OK", "CDP", f"porta {cdp_port} aberta ({latency:.2f} ms TCP)")
            if deep:
                try:
                    pages = await services.session.list_pages()
                    report("OK", "CDP pages", f"{len(pages['pages'])} páginas disponíveis")
                except Exception as exc:
                    report("FALHA", "CDP pages", type(exc).__name__)
                    healthy = False
        report("INFO", "Processos", "nenhum processo foi iniciado ou encerrado")
    finally:
        await services.close()
    if output_json:
        print(json.dumps({"ok": healthy, "checks": checks, "repairs": repairs}, ensure_ascii=False))
    else:
        print("Diagnóstico concluído: " + ("OK" if healthy else "FALHA"))
    return healthy
