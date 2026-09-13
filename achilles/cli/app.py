"""Bootstrap leve: --help não importa transports, Pydantic ou Playwright."""

import argparse
import asyncio
import os
import sys
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
    if argv is None:
        raw_args = sys.argv[1:]
    else:
        raw_args = list(argv)

    # Se chamado sem argumentos (ex: apenas `achilles`), abre o modo interativo por padrão
    if not raw_args:
        raw_args = ["interactive"]

    parser = argparse.ArgumentParser(
        prog="achilles", description="Achilles — Chrome CDP Autonomous Agent & Security Suite"
    )
    parser.add_argument("--version", action="version", version="achilles 2.0.0")
    commands = parser.add_subparsers(dest="command", required=True)

    # 1. Interactive REPL
    interactive_p = commands.add_parser("interactive", aliases=["i", "repl"], help="Inicia console interativo no terminal")
    interactive_p.add_argument("--cdp-port", "-c", type=port, default=9222)

    # 2. Status
    status_p = commands.add_parser("status", help="Exibe status da conexão CDP e métricas")
    status_p.add_argument("--cdp-port", "-c", type=port, default=9222)

    # 3. Pages
    pages_p = commands.add_parser("pages", help="Lista abas e frames abertos no navegador")
    pages_p.add_argument("--cdp-port", "-c", type=port, default=9222)

    # 4. Snapshot
    snap_p = commands.add_parser("snapshot", aliases=["snap"], help="Captura snapshot semântico e elementos interativos")
    snap_p.add_argument("--page-id", type=str, default=None)
    snap_p.add_argument("--limit", type=int, default=200)
    snap_p.add_argument("--cdp-port", "-c", type=port, default=9222)

    # 5. Act
    act_p = commands.add_parser("act", help="Executa ação (click, fill, hover, press, select)")
    act_p.add_argument("action", choices=["click", "fill", "hover", "press", "select"])
    act_p.add_argument("element_ref", type=str)
    act_p.add_argument("value", nargs="?", default=None)
    act_p.add_argument("--page-id", type=str, default=None)
    act_p.add_argument("--cdp-port", "-c", type=port, default=9222)

    # 6. Traffic
    traffic_p = commands.add_parser("traffic", help="Lista requisições HTTP capturadas")
    traffic_p.add_argument("--page-id", type=str, default=None)
    traffic_p.add_argument("--limit", type=int, default=50)
    traffic_p.add_argument("--cdp-port", "-c", type=port, default=9222)

    # 7. cURL
    curl_p = commands.add_parser("curl", help="Exporta requisição como comando cURL seguro")
    curl_p.add_argument("request_id", type=str)
    curl_p.add_argument("--shell", choices=["posix", "powershell"], default="powershell" if sys.platform == "win32" else "posix")
    curl_p.add_argument("--cdp-port", "-c", type=port, default=9222)

    # 8. Audit
    audit_p = commands.add_parser("audit", help="Executa auditoria de postura OWASP e segurança")
    audit_p.add_argument("--page-id", type=str, default=None)
    audit_p.add_argument("--cdp-port", "-c", type=port, default=9222)

    # 9. Start REST API
    start_p = commands.add_parser("start", help="Inicia REST Bridge autenticado em 127.0.0.1")
    start_p.add_argument("--port", "-p", type=port, default=8765)
    start_p.add_argument("--cdp-port", "-c", type=port, default=9222)
    start_p.add_argument("--host", choices=["127.0.0.1"], default="127.0.0.1")

    # 10. MCP stdio
    mcp_p = commands.add_parser("mcp", help="Inicia MCP via stdio")
    mcp_p.add_argument("--cdp-port", "-c", type=port, default=9222)

    args = parser.parse_args(raw_args)

    try:
        if args.command in ("interactive", "i", "repl"):
            from achilles.cli.commands import run_interactive
            asyncio.run(run_interactive(args.cdp_port))
        elif args.command == "status":
            from achilles.cli.commands import run_status
            asyncio.run(run_status(args.cdp_port))
        elif args.command == "pages":
            from achilles.cli.commands import run_pages
            asyncio.run(run_pages(args.cdp_port))
        elif args.command in ("snapshot", "snap"):
            from achilles.cli.commands import run_snapshot
            asyncio.run(run_snapshot(args.cdp_port, args.page_id, args.limit))
        elif args.command == "act":
            from achilles.cli.commands import run_act
            asyncio.run(run_act(args.cdp_port, args.action, args.element_ref, args.value, args.page_id))
        elif args.command == "traffic":
            from achilles.cli.commands import run_traffic
            asyncio.run(run_traffic(args.cdp_port, args.page_id, args.limit))
        elif args.command == "curl":
            from achilles.cli.commands import run_curl
            asyncio.run(run_curl(args.cdp_port, args.request_id, args.shell))
        elif args.command == "audit":
            from achilles.cli.commands import run_audit
            asyncio.run(run_audit(args.cdp_port, args.page_id))
        elif args.command == "start":
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
        elif args.command == "mcp":
            from achilles.mcp.server import run_mcp_stdio
            asyncio.run(run_mcp_stdio(args.cdp_port))
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass


if __name__ == "__main__":
    main()
