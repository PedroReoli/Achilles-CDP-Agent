"""Bootstrap leve: --help não importa transports, Pydantic ou Playwright."""

import argparse
import asyncio
import os
import sys
from typing import Optional, Sequence

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def port(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Porta deve ser inteira") from exc
    if not 1 <= number <= 65535:
        raise argparse.ArgumentTypeError("Porta deve estar entre 1 e 65535")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="achilles", description="Achilles — Chrome CDP Autonomous Agent & Security Suite"
    )
    parser.add_argument("--version", action="version", version="achilles 2.1.0")
    parser.add_argument("--lang", "-l", choices=["pt", "en"], default=None, help="Idioma da interface (pt / en)")
    parser.add_argument("--ai", action="store_true", help="Exibe o protocolo autônomo para agentes de IA")

    commands = parser.add_subparsers(dest="command", required=True)

    # 1. Interactive REPL
    interactive_p = commands.add_parser("interactive", aliases=["i", "repl"], help="Inicia console interativo no terminal")
    interactive_p.add_argument("--cdp-port", "-c", type=port, default=9222)
    interactive_p.add_argument("--lang", "-l", choices=["pt", "en"], default=None, help="Idioma da interface (pt / en)")

    # 2. Status
    status_p = commands.add_parser("status", help="Exibe status da conexão CDP e métricas")
    status_p.add_argument("--cdp-port", "-c", type=port, default=9222)

    # 3. Pages
    pages_p = commands.add_parser("pages", help="Lista abas e frames abertos no navegador")
    pages_p.add_argument("--cdp-port", "-c", type=port, default=9222)
    pages_p.add_argument("--lang", "-l", choices=["pt", "en"], default=None)

    # 3b. Open / Navigate
    open_p = commands.add_parser("open", aliases=["nav", "navigate"], help="Navega a aba para uma URL")
    open_p.add_argument("url", type=str, help="URL de destino (ex: https://news.ycombinator.com)")
    open_p.add_argument("--page-id", type=str, default=None)
    open_p.add_argument("--cdp-port", "-c", type=port, default=9222)
    open_p.add_argument("--lang", "-l", choices=["pt", "en"], default=None)

    # 4. Snapshot
    snap_p = commands.add_parser("snapshot", aliases=["snap"], help="Captura snapshot semântico e elementos interativos")
    snap_p.add_argument("--page-id", type=str, default=None)
    snap_p.add_argument("--limit", type=int, default=200)
    snap_p.add_argument("--format", choices=["compact", "json", "markdown"], default="compact")
    snap_p.add_argument("--viewport-only", action="store_true", default=True)
    snap_p.add_argument("--no-viewport-only", action="store_false", dest="viewport_only")
    snap_p.add_argument("--selector", type=str, default=None)
    snap_p.add_argument("--cdp-port", "-c", type=port, default=9222)
    snap_p.add_argument("--lang", "-l", choices=["pt", "en"], default=None)

    # 5. Read (Reader Mode)
    read_p = commands.add_parser("read", aliases=["reader"], help="Lê conteúdo da página em Markdown limpo (Reader Mode, ~95%% economia de tokens)")
    read_p.add_argument("--page-id", type=str, default=None)
    read_p.add_argument("--max-length", type=int, default=50000)
    read_p.add_argument("--cdp-port", "-c", type=port, default=9222)
    read_p.add_argument("--lang", "-l", choices=["pt", "en"], default=None)

    # 6. Report
    report_p = commands.add_parser("report", aliases=["rep"], help="Exibe relatório executivo de economia de tokens e tráfego de rotas")
    report_p.add_argument("--page-id", type=str, default=None)
    report_p.add_argument("--cdp-port", "-c", type=port, default=9222)
    report_p.add_argument("--lang", "-l", choices=["pt", "en"], default=None)

    # 7. Protocol / AI
    proto_p = commands.add_parser("protocol", aliases=["ai"], help="Exibe o protocolo autônomo para agentes de IA")
    proto_p.add_argument("--lang", "-l", choices=["pt", "en"], default=None)

    # 8. Act
    act_p = commands.add_parser("act", help="Executa ação (click, fill, hover, press, select, scroll)")
    act_p.add_argument("action", choices=["click", "fill", "hover", "press", "select", "scroll"])
    act_p.add_argument("element_ref", type=str)
    act_p.add_argument("value", nargs="?", default=None)
    act_p.add_argument("--page-id", type=str, default=None)
    act_p.add_argument("--cdp-port", "-c", type=port, default=9222)
    act_p.add_argument("--lang", "-l", choices=["pt", "en"], default=None)

    # 9. Traffic
    traffic_p = commands.add_parser("traffic", help="Lista requisições HTTP capturadas")
    traffic_p.add_argument("--page-id", type=str, default=None)
    traffic_p.add_argument("--limit", type=int, default=50)
    traffic_p.add_argument("--cdp-port", "-c", type=port, default=9222)
    traffic_p.add_argument("--lang", "-l", choices=["pt", "en"], default=None)

    # 10. cURL
    curl_p = commands.add_parser("curl", help="Exporta requisição como comando cURL seguro")
    curl_p.add_argument("request_id", type=str)
    curl_p.add_argument("--shell", choices=["posix", "powershell"], default="powershell" if sys.platform == "win32" else "posix")
    curl_p.add_argument("--cdp-port", "-c", type=port, default=9222)
    curl_p.add_argument("--lang", "-l", choices=["pt", "en"], default=None)

    # 11. Audit
    audit_p = commands.add_parser("audit", help="Executa auditoria de postura OWASP e segurança")
    audit_p.add_argument("--page-id", type=str, default=None)
    audit_p.add_argument("--cdp-port", "-c", type=port, default=9222)
    audit_p.add_argument("--lang", "-l", choices=["pt", "en"], default=None)

    # 12. Start REST API
    start_p = commands.add_parser("start", help="Inicia REST Bridge autenticado em 127.0.0.1")
    start_p.add_argument("--port", "-p", type=port, default=8765)
    start_p.add_argument("--cdp-port", "-c", type=port, default=9222)
    start_p.add_argument("--host", choices=["127.0.0.1"], default="127.0.0.1")

    # 13. MCP stdio
    mcp_p = commands.add_parser("mcp", help="Inicia MCP via stdio")
    mcp_p.add_argument("--cdp-port", "-c", type=port, default=9222)

    # 14. Doctor
    doctor_p = commands.add_parser("doctor", help="Executa testes de integridade e diagnósticos de produção")
    doctor_p.add_argument("--deep", action="store_true", help="Executa testes de estresse pesados")
    doctor_p.add_argument("--cdp-port", "-c", type=port, default=9222)

    # 15. Wait Challenge
    wc_p = commands.add_parser("wait-challenge", aliases=["challenge", "wait-human"], help="Aguarda resolução cooperativa de Turnstile, CAPTCHA ou 2FA")
    wc_p.add_argument("--page-id", type=str, default=None)
    wc_p.add_argument("--timeout", "-t", type=int, default=120)
    wc_p.add_argument("--cdp-port", "-c", type=port, default=9222)
    wc_p.add_argument("--lang", "-l", choices=["pt", "en"], default=None)

    # 16. Domain Memory
    mem_p = commands.add_parser("memory", aliases=["mem"], help="Gerencia e consulta memória semântica de rotas e autenticação")
    mem_p.add_argument("domain", nargs="?", default=None, help="Domínio para consulta (ex: github.com)")
    mem_p.add_argument("--cdp-port", "-c", type=port, default=9222)
    mem_p.add_argument("--lang", "-l", choices=["pt", "en"], default=None)

    # 17. Export HTML Report
    exp_p = commands.add_parser("export-report", aliases=["export", "dashboard"], help="Gera e exporta dashboard HTML standalone da sessão")
    exp_p.add_argument("--output", "-o", type=str, default="achilles_session_report.html", help="Caminho do arquivo HTML")
    exp_p.add_argument("--page-id", type=str, default=None)
    exp_p.add_argument("--cdp-port", "-c", type=port, default=9222)
    exp_p.add_argument("--lang", "-l", choices=["pt", "en"], default=None)

    bookmarks_p = commands.add_parser("bookmarks", help="Gerencia favoritos do Chrome/Edge conectado")
    bookmarks_p.add_argument("--cdp-port", "-c", type=port, default=9222)
    bookmark_actions = bookmarks_p.add_subparsers(dest="bookmark_operation", required=True)
    list_p = bookmark_actions.add_parser("list", help="Lista pastas ou filhos de uma pasta")
    list_p.add_argument("--parent-id", default=None)
    list_p.add_argument("--limit", type=int, default=100)
    search_p = bookmark_actions.add_parser("search", help="Busca por título ou URL")
    search_p.add_argument("query")
    search_p.add_argument("--limit", type=int, default=100)
    create_p = bookmark_actions.add_parser("create", help="Cria um favorito HTTP(S)")
    create_p.add_argument("title")
    create_p.add_argument("url")
    create_p.add_argument("--parent-id", default=None)
    update_p = bookmark_actions.add_parser("update", help="Edita título ou URL")
    update_p.add_argument("id")
    update_p.add_argument("--title", default=None)
    update_p.add_argument("--url", default=None)
    remove_p = bookmark_actions.add_parser("remove", help="Remove favorito ou pasta vazia")
    remove_p.add_argument("id")

    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    if argv is None:
        raw_args = sys.argv[1:]
    else:
        raw_args = list(argv)

    # Suporte nativo ao modo autônomo imediato via `achilles --ai`
    if "--ai" in raw_args:
        from achilles.cli.commands import run_protocol
        lang = "pt"
        if "-l" in raw_args:
            idx = raw_args.index("-l")
            if idx + 1 < len(raw_args):
                lang = raw_args[idx + 1]
        elif "--lang" in raw_args:
            idx = raw_args.index("--lang")
            if idx + 1 < len(raw_args):
                lang = raw_args[idx + 1]
        run_protocol(lang=lang)
        return

    # Se chamado sem argumentos (ex: apenas `achilles`), abre o modo interativo por padrão
    if not raw_args:
        raw_args = ["interactive"]

    parser = build_parser()
    args = parser.parse_args(raw_args)

    try:
        if getattr(args, "ai", False) or args.command in ("protocol", "ai"):
            from achilles.cli.commands import run_protocol
            run_protocol(getattr(args, "lang", None))
        elif args.command in ("interactive", "i", "repl"):
            from achilles.cli.commands import run_interactive
            asyncio.run(run_interactive(args.cdp_port, getattr(args, "lang", None)))
        elif args.command == "status":
            from achilles.cli.commands import run_status
            from achilles.cli.i18n import I18n
            asyncio.run(run_status(args.cdp_port, I18n(getattr(args, "lang", None))))
        elif args.command == "pages":
            from achilles.cli.commands import run_pages
            from achilles.cli.i18n import I18n
            asyncio.run(run_pages(args.cdp_port, I18n(getattr(args, "lang", None))))
        elif args.command in ("open", "nav", "navigate"):
            from achilles.cli.commands import run_open
            from achilles.cli.i18n import I18n
            asyncio.run(run_open(args.cdp_port, args.url, args.page_id, I18n(getattr(args, "lang", None))))
        elif args.command in ("snapshot", "snap"):
            from achilles.cli.commands import run_snapshot
            from achilles.cli.i18n import I18n
            asyncio.run(
                run_snapshot(
                    args.cdp_port,
                    I18n(getattr(args, "lang", None)),
                    args.page_id,
                    args.limit,
                    format=getattr(args, "format", "compact"),
                    in_viewport_only=getattr(args, "viewport_only", True),
                    selector=getattr(args, "selector", None),
                )
            )
        elif args.command in ("read", "reader"):
            from achilles.cli.commands import run_read
            from achilles.cli.i18n import I18n
            asyncio.run(
                run_read(
                    args.cdp_port,
                    I18n(getattr(args, "lang", None)),
                    args.page_id,
                    args.max_length,
                )
            )
        elif args.command in ("report", "rep"):
            from achilles.cli.commands import run_report
            from achilles.cli.i18n import I18n
            asyncio.run(
                run_report(
                    args.cdp_port,
                    I18n(getattr(args, "lang", None)),
                    args.page_id,
                )
            )
        elif args.command == "act":
            from achilles.cli.commands import run_act
            from achilles.cli.i18n import I18n
            asyncio.run(run_act(args.cdp_port, args.action, args.element_ref, args.value, args.page_id, I18n(getattr(args, "lang", None))))
        elif args.command == "traffic":
            from achilles.cli.commands import run_traffic
            from achilles.cli.i18n import I18n
            asyncio.run(run_traffic(args.cdp_port, I18n(getattr(args, "lang", None)), args.page_id, args.limit))
        elif args.command == "curl":
            from achilles.cli.commands import run_curl
            from achilles.cli.i18n import I18n
            asyncio.run(run_curl(args.cdp_port, args.request_id, args.shell, I18n(getattr(args, "lang", None))))
        elif args.command == "audit":
            from achilles.cli.commands import run_audit
            from achilles.cli.i18n import I18n
            asyncio.run(run_audit(args.cdp_port, I18n(getattr(args, "lang", None)), args.page_id))
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
        elif args.command == "doctor":
            from achilles.cli.doctor import run_doctor
            if not asyncio.run(run_doctor(args.cdp_port, args.deep)):
                raise SystemExit(1)
        elif args.command in ("wait-challenge", "challenge", "wait-human"):
            from achilles.cli.commands import run_wait_challenge
            from achilles.cli.i18n import I18n

            asyncio.run(
                run_wait_challenge(
                    args.cdp_port,
                    I18n(getattr(args, "lang", None)),
                    args.page_id,
                    args.timeout,
                )
            )
        elif args.command in ("memory", "mem"):
            from achilles.cli.commands import run_domain_memory
            from achilles.cli.i18n import I18n

            asyncio.run(
                run_domain_memory(
                    args.cdp_port,
                    I18n(getattr(args, "lang", None)),
                    args.domain,
                )
            )
        elif args.command in ("export-report", "export", "dashboard"):
            from achilles.cli.commands import run_export_report
            from achilles.cli.i18n import I18n

            asyncio.run(
                run_export_report(
                    args.cdp_port,
                    I18n(getattr(args, "lang", None)),
                    args.page_id,
                    args.output,
                )
            )
        elif args.command == "bookmarks":
            from achilles.cli.bookmarks import run_bookmarks

            fields = {
                "list": ("parent_id", "limit"),
                "search": ("query", "limit"),
                "create": ("title", "url", "parent_id"),
                "update": ("id", "title", "url"),
                "remove": ("id",),
            }[args.bookmark_operation]
            arguments = {field: getattr(args, field) for field in fields}
            asyncio.run(run_bookmarks(args.cdp_port, args.bookmark_operation, arguments))
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass


if __name__ == "__main__":
    main()
