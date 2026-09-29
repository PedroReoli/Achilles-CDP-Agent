"""Diagnóstico não destrutivo das dependências, do MCP e do endpoint CDP."""

import asyncio
import importlib.metadata
import sys
import time

from achilles.mcp.server import MCPServer
from achilles.services.application import ApplicationServices


async def measure_cdp_latency(cdp_port: int) -> float:
    started = time.perf_counter()
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", cdp_port), 1)
        writer.close()
        await writer.wait_closed()
        return (time.perf_counter() - started) * 1000
    except (OSError, asyncio.TimeoutError):
        return -1


async def run_doctor(cdp_port: int, deep: bool) -> bool:
    """Chrome desligado é estado operacional permitido; falhas da suíte retornam False."""
    print("Achilles CDP Agent — Diagnóstico")
    healthy = sys.version_info >= (3, 9)
    print(f"{'OK' if healthy else 'FALHA'} Python {sys.version_info.major}.{sys.version_info.minor}")
    for package in ("playwright", "pydantic", "fastapi", "rich"):
        try:
            print(f"OK {package} {importlib.metadata.version(package)}")
        except importlib.metadata.PackageNotFoundError:
            print(f"FALHA {package}: dependência ausente")
            healthy = False

    services = ApplicationServices(cdp_port)
    try:
        server = MCPServer(services)
        response = await server.handle({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        })
        tools = await server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        if response and tools and tools.get("result", {}).get("tools"):
            print(f"OK MCP: {len(tools['result']['tools'])} ferramentas")
        else:
            print("FALHA MCP: handshake ou catálogo indisponível")
            healthy = False

        latency = await measure_cdp_latency(cdp_port)
        if latency < 0:
            print(f"INFO CDP: porta {cdp_port} fechada; partida automática ocorre na primeira operação")
        else:
            print(f"OK CDP: porta {cdp_port} aberta ({latency:.2f} ms de conexão TCP)")
            if deep:
                try:
                    pages = await services.session.list_pages()
                    print(f"OK CDP: {len(pages['pages'])} páginas disponíveis")
                except Exception as exc:
                    print(f"FALHA CDP: {type(exc).__name__}")
                    healthy = False
        print("INFO Processos: nenhum processo foi iniciado ou encerrado pelo diagnóstico")
    finally:
        await services.close()
    print("Diagnóstico concluído: " + ("OK" if healthy else "FALHA"))
    return healthy
