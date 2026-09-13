"""Bootstrap leve: --help não importa transports, Pydantic ou Playwright."""

import argparse
import os
from typing import Optional, Sequence


def port(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Porta deve ser inteira") from exc
    if not 1 <= number <= 65535:
        raise argparse.ArgumentTypeError("Porta deve estar entre 1 e 65535")
    return number


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        prog="achilles", description="Achilles — Chrome CDP Application Services"
    )
    parser.add_argument("--version", action="version", version="achilles 2.0.0")
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start", help="Inicia REST autenticado em 127.0.0.1")
    start.add_argument("--port", "-p", type=port, default=8765)
    start.add_argument("--cdp-port", "-c", type=port, default=9222)
    start.add_argument("--host", choices=["127.0.0.1"], default="127.0.0.1")
    mcp = commands.add_parser("mcp", help="Inicia MCP via stdio")
    mcp.add_argument("--cdp-port", "-c", type=port, default=9222)
    args = parser.parse_args(argv)
    if args.command == "start":
        import uvicorn

        from achilles.api.server import create_app

        uvicorn.run(
            create_app(args.cdp_port, os.environ.get("ACHILLES_API_TOKEN")),
            host="127.0.0.1",
            port=args.port,
            proxy_headers=False,
            log_level="warning",
            limit_concurrency=32,
        )
    else:
        import asyncio

        from achilles.mcp.server import run_mcp_stdio

        asyncio.run(run_mcp_stdio(args.cdp_port))
