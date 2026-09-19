"""Comandos CLI e REPL Interativo do Achilles CDP Agent com i18n (PT/EN) e Perfil Persistente."""

import asyncio
import ctypes
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

# Habilita Virtual Terminal Processing no Windows CMD
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
        kernel32 = ctypes.windll.kernel32
        hStdOut = kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(hStdOut, ctypes.byref(mode))
        mode.value |= 0x0004
        kernel32.SetConsoleMode(hStdOut, mode)
    except Exception:
        pass

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from achilles.cli.i18n import I18n

is_tty = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
console = Console(force_terminal=is_tty, color_system="truecolor" if is_tty else None)

ASCII_BANNER = """
 ▄▄▄       ▄████▄   ██░ ██  ██▓ ██▓     ██▓    ▓█████   ██████ 
▒████▄    ▒██▀ ▀█  ▓██░ ██▒▓██▒▓██▒    ▓██▒    ▓█   ▀ ▒██    ▒ 
▒██  ▀█▄  ▒▓█    ▄ ▒██▀▀██░▒██▒▒██░    ▒██░    ▒███   ░ ▓██▄   
░██▄▄▄▄██ ▒▓▓▄ ▄██▒░▓█ ░██ ░██░▒██░    ▒██░    ▒▓█  ▄   ▒   ██▒
 ▓█   ▓██▒▒ ▓███▀ ░░▓█▒░██▓░██░░██████▒░██████▒░▒████▒▒██████▒▒
 ▒▒   ▓▒█░░ ░▒ ▒  ░ ▒ ░░▒░▒░▓  ░ ▒░▓  ░░ ▒░▓  ░░░ ▒░ ░▒ ▒▓▒ ▒ ░
  ▒   ▒▒ ░  ░  ▒    ▒ ░▒░ ░ ▒ ░░ ░ ▒  ░░ ░ ▒  ░ ░ ░  ░░ ░▒  ░ ░
  ░   ▒   ░         ░  ░░ ░ ▒ ░  ░ ░     ░ ░        ░  ░  ░  ░  
      ░  ░░ ░       ░  ░  ░ ░      ░  ░    ░  ░     ░        ░  
          ░                                                     
"""


def get_chrome_profile_dir() -> Path:
    """Retorna o diretório do perfil persistente do Chrome (salva logins, cookies e sessões)."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Achilles" / "chrome_profile"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "Achilles" / "chrome_profile"
    else:
        base = Path.home() / ".config" / "achilles" / "chrome_profile"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _print_banner(i18n: I18n):
    banner_text = Text.from_markup(f"[bold #c084fc]{ASCII_BANNER}[/]")
    subtitle = Text.from_markup(f"[bold #e9d5ff]{i18n.t('banner_subtitle')}[/]")
    console.print(
        Panel(
            banner_text,
            subtitle=subtitle,
            border_style="#a855f7",
            box=box.ROUNDED,
            padding=(0, 2),
        )
    )


def ensure_chrome_running(cdp_port: int, i18n: I18n):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex(("127.0.0.1", cdp_port)) == 0:
                return None
    except Exception:
        pass

    possible_paths = []
    if sys.platform == "win32":
        possible_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ]
    elif sys.platform == "darwin":
        possible_paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    else:
        for candidate in ("google-chrome", "google-chrome-stable", "chromium-browser", "chromium"):
            found = shutil.which(candidate)
            if found:
                possible_paths.append(found)

    chrome_bin = next((p for p in possible_paths if os.path.exists(p)), None)
    if not chrome_bin and shutil.which("google-chrome"):
        chrome_bin = shutil.which("google-chrome")
    if not chrome_bin and shutil.which("chromium"):
        chrome_bin = shutil.which("chromium")

    if chrome_bin:
        profile_dir = get_chrome_profile_dir()
        console.print(f"[yellow][*][/] {i18n.t('chrome_not_detected')} [bold cyan]{cdp_port}[/].")
        console.print(f"[bold #a855f7][*][/] {i18n.t('starting_persistent_chrome')} [dim cyan]{profile_dir}[/]...")
        console.print(f"[dim green]    ✔ {i18n.t('persistent_profile_info')}[/]")
        
        proc = subprocess.Popen([
            chrome_bin,
            f"--remote-debugging-port={cdp_port}",
            f"--user-data-dir={str(profile_dir)}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-blink-features=AutomationControlled",
            "about:blank"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        for _ in range(30):
            time.sleep(0.2)
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.2)
                    if s.connect_ex(("127.0.0.1", cdp_port)) == 0:
                        break
            except Exception:
                pass
        return proc
    return None


def print_help_table(i18n: I18n):
    table = Table(
        title=f"[bold #e9d5ff]{i18n.t('help_title')}[/]",
        border_style="#a855f7",
        box=box.ROUNDED,
        header_style="bold #c084fc",
        show_lines=True,
    )
    table.add_column(i18n.t("col_category"), style="bold #93c5fd", width=14)
    table.add_column(i18n.t("col_command"), style="bold #c084fc", width=24)
    table.add_column(i18n.t("col_description"), style="#e2e8f0", width=42)
    table.add_column(i18n.t("col_example"), style="dim #38bdf8", width=30)

    table.add_row(
        i18n.t("cat_nav"),
        "/open <url> (ou /goto)",
        i18n.t("desc_open"),
        "/open https://google.com",
    )
    table.add_row(
        i18n.t("cat_nav"),
        "/pages",
        i18n.t("desc_pages"),
        "/pages",
    )
    table.add_row(
        i18n.t("cat_nav"),
        "/select <page_id>",
        i18n.t("desc_select"),
        "/select page_1234",
    )
    table.add_row(
        i18n.t("cat_nav"),
        "/new [url]",
        "Abre nova aba (opcional: URL)",
        "/new https://github.com",
    )
    table.add_row(
        i18n.t("cat_nav"),
        "/close [page_id]",
        "Fecha aba ativa ou especificada",
        "/close",
    )
    table.add_row(
        i18n.t("cat_nav"),
        "/scroll [dir/pixels]",
        i18n.t("desc_scroll"),
        "/scroll down 500",
    )
    table.add_row(
        i18n.t("cat_inspect"),
        "/snapshot (ou /snap)",
        i18n.t("desc_snap"),
        "/snapshot",
    )
    table.add_row(
        i18n.t("cat_inspect"),
        "/read [max_length]",
        i18n.t("desc_read"),
        "/read",
    )
    table.add_row(
        i18n.t("cat_action"),
        "/fill <ref> <texto>",
        i18n.t("desc_fill"),
        "/fill a1b2c3_1 Pedro Lucas",
    )
    table.add_row(
        i18n.t("cat_action"),
        "/click <ref>",
        i18n.t("desc_click"),
        "/click a1b2c3_4",
    )
    table.add_row(
        i18n.t("cat_network"),
        "/traffic [limit]",
        i18n.t("desc_traffic"),
        "/traffic 15",
    )
    table.add_row(
        i18n.t("cat_network"),
        "/curl <req_id>",
        i18n.t("desc_curl"),
        "/curl req_987",
    )
    table.add_row(
        i18n.t("cat_network"),
        "/report",
        i18n.t("desc_report"),
        "/report",
    )
    table.add_row(
        i18n.t("cat_network"),
        "/export [arquivo.html]",
        "Exporta dashboard HTML com KPIs e rotas da sessão",
        "/export relatorio.html",
    )
    table.add_row(
        i18n.t("cat_network"),
        "/memory [domínio]",
        "Consulta memória semântica de rotas e APIs",
        "/memory github.com",
    )
    table.add_row(
        i18n.t("cat_action"),
        "/wait-human [tempo]",
        "Aguarda usuário resolver CAPTCHA/2FA no Chrome",
        "/wait-human 120",
    )
    table.add_row(
        i18n.t("cat_security"),
        "/audit",
        i18n.t("desc_audit"),
        "/audit",
    )
    table.add_row(
        i18n.t("cat_system"),
        "/ai (ou /protocol)",
        i18n.t("desc_ai"),
        "/ai",
    )
    table.add_row(
        i18n.t("cat_system"),
        "/lang <pt|en>",
        i18n.t("desc_lang"),
        "/lang en",
    )
    table.add_row(
        i18n.t("cat_system"),
        "/status",
        i18n.t("desc_status"),
        "/status",
    )
    table.add_row(
        i18n.t("cat_system"),
        "/clear",
        i18n.t("desc_clear"),
        "/clear",
    )
    table.add_row(
        i18n.t("cat_system"),
        "/exit (ou /quit)",
        i18n.t("desc_exit"),
        "/exit",
    )
    console.print(table)


async def run_pages(cdp_port: int, i18n: I18n, services=None, current_page_id: Optional[str] = None) -> None:
    should_close = False
    if services is None:
        from achilles.services.application import ApplicationServices
        services = ApplicationServices(cdp_port)
        should_close = True

    try:
        res = await services.call("browser_list_pages", {})
        pages = res.get("pages", [])
        active_id = current_page_id or res.get("active_page_id") or (pages[0]["page_id"] if pages else None)
        
        if not pages:
            console.print(f"[yellow]{i18n.t('no_pages')}[/]")
            return

        table = Table(
            title=f"[bold #e9d5ff]{i18n.t('open_tabs_title')} ({len(pages)})[/]",
            border_style="#a855f7",
            box=box.ROUNDED,
            header_style="bold #c084fc",
        )
        table.add_column("#", style="bold #c084fc", width=4, justify="center")
        table.add_column(i18n.t("col_status"), width=12, justify="center")
        table.add_column("Page ID", style="bold #e9d5ff", width=22)
        table.add_column("Título / Title", style="#f8fafc", width=32)
        table.add_column("URL", style="cyan", width=42)

        for idx, p in enumerate(pages, start=1):
            is_active = f"[bold green]{i18n.t('active_badge')}[/]" if p.get("page_id") == active_id else f"[dim #64748b]{i18n.t('inactive_badge')}[/]"
            table.add_row(
                str(idx),
                is_active,
                p["page_id"],
                p.get("title", "(Sem título)")[:30],
                p.get("url", "about:blank")[:40],
            )
        console.print(table)
    finally:
        if should_close:
            await services.close()


async def run_snapshot(
    cdp_port: int,
    i18n: I18n,
    page_id: Optional[str] = None,
    limit: int = 200,
    format: str = "compact",
    in_viewport_only: bool = True,
    selector: Optional[str] = None,
    services=None,
) -> None:
    should_close = False
    if services is None:
        from achilles.services.application import ApplicationServices
        services = ApplicationServices(cdp_port)
        should_close = True

    try:
        args: Dict[str, Any] = {
            "limit": limit,
            "format": format,
            "in_viewport_only": in_viewport_only,
        }
        if selector:
            args["selector"] = selector
        if page_id:
            args["page_id"] = page_id
        res = await services.call("browser_snapshot", args)
        elements = res.get("elements", [])
        saved_pct = res.get("tokens_saved_percent", "")

        table = Table(
            title=f"[bold #e9d5ff]{i18n.t('snap_title')} [dim]({len(elements)} {i18n.t('snap_elements_count')})[/][/]",
            subtitle=f"[bold green]✔ Economia de Tokens: {saved_pct} (Viewport)[/]" if saved_pct else None,
            border_style="#a855f7",
            box=box.ROUNDED,
            header_style="bold #c084fc",
        )
        table.add_column(i18n.t("col_ref"), style="bold cyan", width=34)
        table.add_column(i18n.t("col_role"), style="bold #c084fc", width=16)
        table.add_column(i18n.t("col_name"), style="#f8fafc", width=46)
        table.add_column(i18n.t("col_state"), width=14, justify="center")

        for el in elements:
            ref = el.get("element_ref", "")
            role = el.get("role", "element")
            name = el.get("name", "")
            disabled = el.get("disabled", False)
            state = f"[red]{i18n.t('state_disabled')}[/]" if disabled else f"[green]{i18n.t('state_enabled')}[/]"

            role_badge = f"[bold #c084fc]{role}[/]"
            if role in ("button", "link"):
                role_badge = f"[bold green]{role}[/]"
            elif role in ("textbox", "searchbox"):
                role_badge = f"[bold #38bdf8]{role}[/]"
            elif role in ("checkbox", "radio"):
                role_badge = f"[bold #f59e0b]{role}[/]"

            table.add_row(f"[{ref}]", role_badge, str(name)[:44], state)

        console.print(table)
    finally:
        if should_close:
            await services.close()


async def run_traffic(cdp_port: int, i18n: I18n, page_id: Optional[str] = None, limit: int = 50, services=None) -> None:
    should_close = False
    if services is None:
        from achilles.services.application import ApplicationServices
        services = ApplicationServices(cdp_port)
        should_close = True

    try:
        args: Dict[str, Any] = {"limit": limit}
        if page_id:
            args["page_id"] = page_id
        res = await services.call("network_query", args)
        records = res.get("records", [])

        if not records:
            console.print(f"[dim]{i18n.t('traffic_empty')}[/]")
            return

        table = Table(
            title=f"[bold #e9d5ff]{i18n.t('traffic_title')} ({len(records)} items)[/]",
            border_style="#a855f7",
            box=box.ROUNDED,
            header_style="bold #c084fc",
        )
        table.add_column(i18n.t("col_req_id"), style="dim #94a3b8", width=18)
        table.add_column(i18n.t("col_method"), width=10, justify="center")
        table.add_column(i18n.t("col_status"), width=12, justify="center")
        table.add_column(i18n.t("col_url"), style="cyan", width=46)
        table.add_column(i18n.t("col_time"), style="dim #94a3b8", width=10, justify="right")

        for r in records:
            method = r.get("method", "GET")
            m_style = "bold blue" if method == "GET" else ("bold yellow" if method == "POST" else "bold red")
            
            status = r.get("status") or "PEND"
            s_style = "bold green" if str(status).startswith("2") else ("bold yellow" if str(status).startswith("3") else "bold red")
            dur = f"{r.get('duration_ms', 0)}ms"

            table.add_row(
                r.get("request_id", "")[:16],
                f"[{m_style}]{method}[/]",
                f"[{s_style}]{status}[/]",
                r.get("url", "")[:44],
                dur,
            )
        console.print(table)
    finally:
        if should_close:
            await services.close()


async def run_audit(cdp_port: int, i18n: I18n, page_id: Optional[str] = None, services=None) -> None:
    should_close = False
    if services is None:
        from achilles.services.application import ApplicationServices
        services = ApplicationServices(cdp_port)
        should_close = True

    try:
        args: Dict[str, Any] = {}
        if page_id:
            args["page_id"] = page_id
        res = await services.call("security_audit", args)
        score = res.get("security_score")
        findings = res.get("findings", [])

        score_text = f"[bold green]{score}/100 {i18n.t('score_excellent')}[/]" if (score or 0) >= 80 else (
            f"[bold yellow]{score}/100 {i18n.t('score_warning')}[/]" if (score or 0) >= 50 else f"[bold red]{score}/100 {i18n.t('score_critical')}[/]"
        )

        panel_content = Text.from_markup(
            f"[bold #e9d5ff]{i18n.t('security_score')}:[/] {score_text}\n"
            f"[dim #94a3b8]{i18n.t('analyzed_url')}:[/] [cyan]{res.get('url', 'N/A')}[/]\n"
            f"[dim #94a3b8]{i18n.t('total_findings')}:[/] [bold #c084fc]{len(findings)}[/]"
        )
        console.print(Panel(panel_content, title=f"[bold #c084fc]{i18n.t('audit_title')}[/]", border_style="#a855f7", box=box.ROUNDED))

        if findings:
            table = Table(border_style="#a855f7", box=box.ROUNDED, header_style="bold #c084fc")
            table.add_column(i18n.t("col_severity"), width=12, justify="center")
            table.add_column(i18n.t("col_vulnerability"), style="bold #f8fafc", width=32)
            table.add_column(i18n.t("col_desc_rem"), style="#cbd5e1", width=52)

            for f in findings:
                sev = f.get("severity", "info").upper()
                sev_badge = "[bold red]HIGH[/]" if sev in ("HIGH", "CRITICAL") else (
                    "[bold yellow]MEDIUM[/]" if sev == "MEDIUM" else "[dim cyan]LOW[/]"
                )
                desc = f.get("description", "")
                rem = f"\n[bold green]{i18n.t('remediation_label')}:[/] {f.get('remediation', '')}" if f.get("remediation") else ""
                table.add_row(sev_badge, f.get("title", ""), f"{desc}{rem}")
            console.print(table)
    finally:
        if should_close:
            await services.close()


async def run_read(
    cdp_port: int,
    i18n: I18n,
    page_id: Optional[str] = None,
    max_length: int = 50000,
    services=None,
) -> None:
    should_close = False
    if services is None:
        from achilles.services.application import ApplicationServices
        ensure_chrome_running(cdp_port, i18n)
        services = ApplicationServices(cdp_port)
        should_close = True

    try:
        res = await services.call("browser_read_content", {"page_id": page_id, "max_length": max_length})
        metrics = res.get("metrics", {})
        saved_pct = metrics.get("tokens_saved_percent", "0%")
        saved_tokens = max(0, metrics.get("estimated_raw_tokens", 0) - metrics.get("estimated_extracted_tokens", 0))

        header_text = (
            f"[bold cyan]{res.get('title', 'Sem título')}[/]\n"
            f"[dim]{res.get('url', '')}[/]\n"
            f"[bold green]✔ Economia de Tokens: {saved_pct} ({saved_tokens:,} tokens economizados vs HTML bruto)[/]"
        )
        console.print(Panel(header_text, title="[bold #c084fc]📖 Reader Mode (Conteúdo Extraído)[/]", border_style="#a855f7", box=box.ROUNDED))
        console.print(res.get("markdown", ""))
    finally:
        if should_close:
            await services.close()


async def run_report(
    cdp_port: int,
    i18n: I18n,
    page_id: Optional[str] = None,
    services=None,
) -> None:
    should_close = False
    if services is None:
        from achilles.services.application import ApplicationServices
        ensure_chrome_running(cdp_port, i18n)
        services = ApplicationServices(cdp_port)
        should_close = True

    try:
        rep = await services.call("browser_report", {"page_id": page_id})
        tm = rep.get("token_metrics", {})
        rr = rep.get("routes_report", {})

        # Table 1: Token Metrics
        t_tokens = Table(title="[bold #c084fc]⚡ Token-Zero-Waste & Economia de Custos[/]", border_style="#a855f7", box=box.ROUNDED)
        t_tokens.add_column("Métrica", style="bold #93c5fd", width=34)
        t_tokens.add_column("Valor", style="#e2e8f0", width=34)
        t_tokens.add_row("Snapshots Compactos Executados", str(tm.get("total_snapshots", 0)))
        t_tokens.add_row("Páginas Lidas em Reader Mode", str(tm.get("total_reads", 0)))
        t_tokens.add_row("Tokens Brutos Evitados", f"[bold green]{tm.get('raw_tokens_avoided', 0):,}[/]")
        t_tokens.add_row("Tokens Efetivamente Consumidos", f"{tm.get('tokens_consumed_estimated', 0):,}")
        t_tokens.add_row("Taxa Global de Economia", f"[bold green]{tm.get('overall_savings_percent', '0%')}[/]")
        console.print(t_tokens)

        # Table 2: Routes Report
        t_routes = Table(title="[bold #c084fc]🌐 Rotas & APIs de Rede Analisadas[/]", border_style="#38bdf8", box=box.ROUNDED)
        t_routes.add_column("Categoria / Métrica", style="bold #93c5fd", width=34)
        t_routes.add_column("Detalhe", style="#e2e8f0", width=40)
        t_routes.add_row("Total de Requisições Gravadas", str(rr.get("total_requests", 0)))
        t_routes.add_row("Domínios Únicos Contactados", str(rr.get("unique_domains_count", 0)))
        t_routes.add_row("Endpoints de API Detectados", str(rr.get("api_endpoints_detected", 0)))
        
        status_dist = rr.get("status_distribution", {})
        dist_str = f"2xx: [green]{status_dist.get('2xx', 0)}[/] | 3xx: [yellow]{status_dist.get('3xx', 0)}[/] | 4xx: [red]{status_dist.get('4xx', 0)}[/] | 5xx: [bold red]{status_dist.get('5xx', 0)}[/]"
        t_routes.add_row("Distribuição de Status HTTP", dist_str)
        console.print(t_routes)

        # Print top API routes if detected
        apis = rr.get("api_endpoints", [])
        if apis:
            t_api = Table(title="[bold #c084fc]🔍 Rotas de API Detectadas (Amostra)[/]", border_style="#a855f7", box=box.ROUNDED)
            t_api.add_column("Método", style="bold yellow", width=8)
            t_api.add_column("Host", style="#93c5fd", width=25)
            t_api.add_column("Path", style="#e2e8f0", width=35)
            t_api.add_column("Status", style="green", width=8)
            for a in apis[:10]:
                t_api.add_row(a.get("method"), a.get("host"), a.get("path")[:35], str(a.get("status", "-")))
            console.print(t_api)

        # Stealth panel
        stealth_info = (
            "[bold green]✔ Chromium Automation Controlled Desativado[/] (--disable-blink-features=AutomationControlled)\n"
            "[bold green]✔ Navigator Webdriver Mascarado[/] (undefined injetado em todas as abas e frames)\n"
            "[bold green]✔ Canvas 2D & WebGL Stealth[/] (Ruído imperceptível de pixel + spoofing NVIDIA RTX 3060)\n"
            "[bold green]✔ Web Audio API Stealth[/] (Micro-jitter em AudioBuffer contra fingerprinting acústico)\n"
            "[bold green]✔ Floating In-Browser HUD[/] (Closed Shadow DOM isolado com status colaborativo)\n"
            "[bold green]✔ Perfil Persistente de Usuário Ativo[/] (Cookies, logins e sessões preservados)\n"
            "[bold green]✔ Redação Zero-Secret Ativa[/] (Senhas, Bearer tokens e chaves mascarados)"
        )
        console.print(Panel(stealth_info, title="[bold #c084fc]🛡️ Postura Anti-Bot & Anti-Detection Multi-Superfície[/]", border_style="green", box=box.ROUNDED))
    finally:
        if should_close:
            await services.close()


async def run_wait_challenge(
    cdp_port: int,
    i18n: I18n,
    page_id: Optional[str] = None,
    timeout_s: int = 120,
    services=None,
) -> None:
    should_close = False
    if services is None:
        from achilles.services.application import ApplicationServices
        ensure_chrome_running(cdp_port, i18n)
        services = ApplicationServices(cdp_port)
        should_close = True

    try:
        console.print(f"[bold yellow][!][/] [bold #e9d5ff]Monitorando desafios anti-bot / 2FA / Login...[/]")
        console.print(f"[dim #94a3b8]    Se houver CAPTCHA ou login na janela do Chrome, resolva diretamente no navegador.[/]")
        res = await services.call(
            "browser_wait_for_challenge", {"page_id": page_id, "timeout_s": timeout_s}
        )
        status = res.get("status")
        if status in ("resolved", "resolved_by_navigation"):
            console.print(f"[bold green][✓][/] [bold #f8fafc]{res.get('message')}[/] ([dim]{res.get('elapsed_s')}s[/])")
        elif status == "already_clear":
            console.print(f"[bold cyan][i][/] [bold #f8fafc]{res.get('message')}[/]")
        elif status == "timeout":
            console.print(f"[bold red][!][/] [yellow]{res.get('message')}[/]")
        else:
            console.print(f"[yellow]{res.get('message')}[/]")
    finally:
        if should_close:
            await services.close()


async def run_domain_memory(
    cdp_port: int,
    i18n: I18n,
    domain: Optional[str] = None,
    services=None,
) -> None:
    should_close = False
    if services is None:
        from achilles.services.application import ApplicationServices
        services = ApplicationServices(cdp_port)
        should_close = True

    try:
        if domain:
            res = await services.call(
                "browser_domain_memory", {"operation": "get", "domain": domain}
            )
            mem = res.get("memory") or res
            table = Table(title=f"[bold #c084fc]🧠 Memória Semântica: {domain}[/]", border_style="#a855f7", box=box.ROUNDED)
            table.add_column("Propriedade", style="bold #93c5fd", width=25)
            table.add_column("Valor", style="#f8fafc", width=50)
            table.add_row("Autenticado", "[green]Sim[/]" if mem.get("authenticated") else "[yellow]Não[/]")
            table.add_row("Atalhos", json.dumps(mem.get("shortcuts", {}), ensure_ascii=False))
            table.add_row("APIs Conhecidas", f"{len(mem.get('api_endpoints', []))} rotas")
            table.add_row("Notas", " | ".join(mem.get("notes", [])) or "Nenhuma")
            console.print(table)
        else:
            res = await services.call("browser_domain_memory", {"operation": "list"})
            domains = res.get("domains", [])
            if not domains:
                console.print("[dim yellow]Nenhuma memória semântica gravada ainda.[/]")
                return
            table = Table(title=f"[bold #c084fc]🧠 Memórias de Domínio Registradas ({len(domains)})[/]", border_style="#a855f7", box=box.ROUNDED)
            table.add_column("Domínio", style="bold cyan", width=30)
            table.add_column("Autenticado", width=14, justify="center")
            table.add_column("Atalhos", style="#e2e8f0", width=20)
            table.add_column("Rotas de API", style="#94a3b8", width=15)
            for d in domains:
                auth_str = "[bold green]SIM[/]" if d.get("authenticated") else "[dim yellow]NÃO[/]"
                table.add_row(
                    d.get("domain", ""),
                    auth_str,
                    f"{len(d.get('shortcuts', {}))} atalhos",
                    f"{len(d.get('api_endpoints', []))} APIs",
                )
            console.print(table)
    finally:
        if should_close:
            await services.close()


async def run_export_report(
    cdp_port: int,
    i18n: I18n,
    page_id: Optional[str] = None,
    output_path: Optional[str] = None,
    services=None,
) -> None:
    should_close = False
    if services is None:
        from achilles.services.application import ApplicationServices
        ensure_chrome_running(cdp_port, i18n)
        services = ApplicationServices(cdp_port)
        should_close = True

    try:
        target_path = output_path or "achilles_session_report.html"
        res = await services.call(
            "browser_export_html_report", {"page_id": page_id, "output_path": target_path}
        )
        filepath = res.get("filepath", target_path)
        console.print(
            f"[bold green][✓][/] [bold #f8fafc]Dashboard HTML exportado com sucesso:[/] [bold cyan]{filepath}[/]"
        )
    finally:
        if should_close:
            await services.close()


def run_protocol(lang: Optional[str] = None) -> None:
    from achilles.cli.i18n import get_stored_language
    is_pt = lang == "pt" or (lang is None and get_stored_language() == "pt")
    if is_pt:
        protocol_md = """# PROTOCOLO AGENTE AUTÔNOMO ACHILLES (v2.0)

Você está conectado ao Achilles CDP Agent — o facilitador universal de navegação furtiva e colaboração humano-IA no Chrome.

## 1. PRINCÍPIOS FUNDAMENTAIS DE OPERAÇÃO

### 🔒 REGRA ZERO-SECRET (NAVEGAÇÃO COLABORATIVA)
- Quando encontrar telas de login (Google, Meta, Twitter/X, LinkedIn, bancos, 2FA ou CAPTCHAs):
  - **NÃO tente adivinhar credenciais e NUNCA solicite senhas ao usuário no prompt.**
  - **INSTRUÇÃO AO USUÁRIO**: Diga ao usuário: *"Por favor, realize o login / resolva o desafio diretamente na janela do Chrome aberta ao lado; assim que concluir, continuarei a tarefa autonomamente."*
  - O usuário faz login no navegador real. O Achilles usa um perfil persistente (`chrome_profile`), mantendo cookies e sessões de forma nativa e segura.
  - O Achilles possui engine de redação estrita: senhas, Bearer tokens, cookies e chaves de API são automaticamente mascarados como `[REDACTED]` e NUNCA vazam para o seu contexto de IA.
  - Após o usuário logar, assuma o controle da navegação e conclua o objetivo.

### ⚡ TOKEN-ZERO-WASTE (MÁXIMA EFICIÊNCIA DE TOKENS)
- **Para ler conteúdo/artigos/documentação**: SEMPRE execute `achilles read` (Reader Mode limpo em Markdown, reduzindo ~95% do consumo de tokens em comparação ao HTML bruto).
- **Para interagir com elementos**: Execute `achilles snapshot --limit 50` (retorna sintaxe compacta linear: `[@ref] role "nome" (detalhes)` apenas dos elementos visíveis no viewport atual).
- **Para isolar um formulário ou seção**: Use `achilles snapshot --selector "form"` ou `achilles snapshot --selector "#feed"`.

### 🛡️ MODO FURTIVO ANTI-BOT & ANTI-DETECTION
- O Chrome é executado com flags nativas contra detecção (`--disable-blink-features=AutomationControlled`), `navigator.webdriver = undefined`, mocks de runtime do Chrome e digitação com ritmo humano.
- Evite rajadas instantâneas de múltiplos cliques; adote pausas naturais de 1 a 2 segundos entre passos complexos.

---

## 2. GUIA DE COMANDOS CLI PARA AGENTES

| Objetivo | Comando CLI | Descrição |
|---|---|---|
| Listar Abas | `achilles pages` | Lista abas abertas, títulos, URLs e `page_id` ativo |
| Ler Conteúdo | `achilles read` | Extrai o texto principal da página em Markdown limpo |
| Ver Elementos | `achilles snapshot` | Exibe elementos clicáveis/interativos do viewport atual |
| Clicar | `achilles act click <ref>` | Clica no elemento (ex: `achilles act click page_abc/1`) |
| Digitar | `achilles act fill <ref> "<texto>"` | Digita texto no campo com cadência humanizada |
| Pressionar Tecla | `achilles act press <ref> "Enter"` | Envia teclas de controle (Enter, Tab, Escape) |
| Rolar Página | `achilles act scroll down` | Rola a página para baixo para carregar feeds infinitos |
| Ver Tráfego | `achilles traffic` | Lista requisições HTTP da página redigidas |
| Relatório | `achilles report` | Exibe métricas de tokens economizados e rotas de API |
| Aguardar Humano | `achilles wait-challenge` | Aguarda resolução cooperativa de Turnstile/CAPTCHA/2FA |
| Memória de Domínio | `achilles memory` | Consulta atalhos e histórico semântico do domínio |
| Exportar Dashboard | `achilles export-report` | Exporta relatório HTML dark-mode com KPIs e rotas |
| Auditoria OWASP | `achilles audit` | Executa auditoria de segurança da aba ativa |

---

## 3. PROTOCOLOS DE COMUNICAÇÃO AVANÇADOS

- **Servidor MCP stdio**: Inicie com `achilles mcp` para integrar com Claude Code, Cursor ou agentes compatíveis com MCP.
- **REST Bridge Local**: Inicie com `achilles start --port 8765` para consultar rotas JSON autenticadas (`/api/read`, `/api/dom/tree`, `/api/action/click`, `/api/report`, `/api/report/html`, `/api/challenge/wait`, `/api/memory`).

Execute os comandos diretamente via terminal para cumprir a missão designada de forma autônoma.
"""
    else:
        protocol_md = """# ACHILLES CDP AGENT — AUTONOMOUS AGENT PROTOCOL (v2.0)

You are operating the Achilles CDP Agent, an autonomous, anti-detection browser bridge designed for AI agents cooperating with human users.

## 1. CORE OPERATING PRINCIPLES

### 🔒 ZERO-SECRET RULE (HUMAN-AI COLLABORATION)
- When visiting services requiring authentication (Google, Meta, Twitter/X, LinkedIn, banking, 2FA, CAPTCHAs):
  - **NEVER prompt the user to input passwords in CLI or chat.**
  - **INSTRUCT THE USER**: State: *"Please complete the login or captcha challenge directly on the open Chrome browser window; once finished, I will resume the workflow autonomously."*
  - The human logs in securely in genuine Chrome. Achilles uses a persistent profile (`chrome_profile`), preserving cookies and sessions safely across runs.
  - Achilles automatically redacts passwords, Bearer tokens, cookies, and secret keys as `[REDACTED]`. They NEVER leak into your AI prompt context.
  - Once authenticated, take over navigation to complete the user's objective.

### ⚡ TOKEN-ZERO-WASTE ENGINE
- **To read pages, articles, docs, or feeds**: ALWAYS execute `achilles read` (extracts clean Markdown via Reader Mode, saving ~95% tokens vs raw HTML).
- **To inspect interactive UI elements**: Run `achilles snapshot --limit 50` (returns compact linear syntax: `[@ref] role "name" (details)` strictly within the current viewport).
- **To isolate a specific container**: Use `achilles snapshot --selector "form"` or `achilles snapshot --selector "#feed"`.

### 🛡️ ANTI-BOT STEALTH & HUMANIZED CADENCE
- Chrome runs with multi-surface stealth flags (`--disable-blink-features=AutomationControlled`), masked `navigator.webdriver = undefined`, Canvas 2D pixel noise, WebGL NVIDIA spoofing, Web Audio micro-jitter, and closed Shadow DOM HUD.
- Avoid instant machine bursts; use realistic 1-2s pauses between complex actions.

---

## 2. AGENT CLI COMMAND CHEAT SHEET

| Goal | CLI Command | Description |
|---|---|---|
| List Tabs | `achilles pages` | Lists open tabs, titles, sanitized URLs, and `page_id` |
| Read Content | `achilles read` | Reader Mode: clean Markdown content (~95% token savings) |
| Inspect Viewport | `achilles snapshot` | Compact list of interactive elements with `[@ref]` |
| Click Element | `achilles act click <ref>` | Clicks element by its reference (e.g., `page_abc/1`) |
| Fill Input | `achilles act fill <ref> "<value>"` | Types into field with humanized key cadence |
| Press Key | `achilles act press <ref> "Enter"` | Simulates Enter, Tab, Escape, etc. |
| Scroll | `achilles act scroll down` | Scrolls viewport down to trigger lazy loading |
| Inspect Traffic | `achilles traffic` | Lists captured, sanitized HTTP exchanges |
| View Report | `achilles report` | Executive report of tokens saved & analyzed API routes |
| Wait Human | `achilles wait-challenge` | Waits cooperatively for human resolution of Turnstile/CAPTCHA/2FA |
| Domain Memory | `achilles memory` | Queries domain shortcuts, auth status, and API routes |
| Export Dashboard | `achilles export-report` | Exports standalone dark-mode HTML report with KPIs and APIs |
| OWASP Audit | `achilles audit` | Security posture and response header check |

---

## 3. INTEGRATION TRANSPORTS

- **MCP stdio**: Run `achilles mcp` for seamless Model Context Protocol connection.
- **REST Bridge**: Run `achilles start --port 8765` for authenticated local HTTP endpoints (`/api/read`, `/api/dom/tree`, `/api/action/click`, `/api/report`).

Run these CLI commands directly in your terminal to autonomously execute the user's instructions.
"""
    print(protocol_md)


async def run_interactive(cdp_port: int, lang: Optional[str] = None) -> None:
    from achilles.services.application import ApplicationServices
    i18n = I18n(lang)
    _print_banner(i18n)
    ensure_chrome_running(cdp_port, i18n)
    console.print(f"[bold #a855f7][*][/] {i18n.t('connecting')} [bold cyan]{cdp_port}[/]...")
    
    services = ApplicationServices(cdp_port)
    current_page_id: Optional[str] = None
    current_url: str = "about:blank"
    latest_snapshot: Optional[Dict[str, Any]] = None

    # Tenta obter ou abrir a primeira aba para NUNCA ficar em (sem aba)
    for _ in range(15):
        try:
            res_pages = await services.call("browser_list_pages", {})
            pages = res_pages.get("pages", [])
            if pages:
                current_page_id = res_pages.get("active_page_id") or pages[0]["page_id"]
                current_url = next((p["url"] for p in pages if p["page_id"] == current_page_id), "about:blank")
                break
            else:
                page_id, page_obj = await services.session.page()
                current_page_id = page_id
                current_url = "about:blank"
                break
        except Exception:
            await asyncio.sleep(0.3)

    console.print(f"[bold green][✓][/] [bold #e9d5ff]{i18n.t('connected')}[/]")
    console.print(f"[dim #94a3b8]    {i18n.t('type_help')}[/]\n")

    try:
        while True:
            try:
                short_url = current_url.replace("https://", "").replace("http://", "")[:28]
                lang_badge = f"[dim #93c5fd]{i18n.lang.upper()}[/]"
                prompt_str = f"[bold #a855f7]🔮 achilles[/] [dim #64748b]│[/] {lang_badge} [dim #64748b]│[/] [bold #38bdf8]{short_url or 'about:blank'}[/] [bold #c084fc]❯[/] "
                console.print(prompt_str, end="")
                raw = await asyncio.to_thread(input, "")
            except (EOFError, KeyboardInterrupt):
                break
            
            line = raw.strip()
            if not line:
                continue
            
            parts = line.split()
            raw_cmd = parts[0].lower()
            cmd = raw_cmd[1:] if raw_cmd.startswith("/") else raw_cmd
            args = parts[1:]

            if cmd in ("exit", "quit", "q"):
                break
            elif cmd in ("help", "h", "?"):
                print_help_table(i18n)
            elif cmd in ("lang", "idioma"):
                if args:
                    new_lang = args[0].lower()
                    i18n.set_lang(new_lang)
                else:
                    new_lang = "en" if i18n.lang == "pt" else "pt"
                    i18n.set_lang(new_lang)
                console.print(f"[bold green][✓][/] {i18n.t('lang_switched')}")
            elif cmd == "clear":
                os.system("cls" if os.name == "nt" else "clear")
            elif cmd == "status":
                status = await services.call("browser_status", {})
                panel_content = Text.from_markup(
                    f"[bold #a855f7]CDP Endpoint:[/] [cyan]{status.get('cdp_url')}[/]\n"
                    f"[bold #a855f7]Modo / Mode:[/] [green]{status.get('mode')}[/]\n"
                    f"[bold #a855f7]Reqs Gravadas:[/] [bold #c084fc]{status.get('recorded_requests')}[/]\n"
                    f"[bold #a855f7]Geração / Generation:[/] {status.get('generation')}\n"
                    f"[bold #a855f7]Profile Dir:[/] [dim cyan]{get_chrome_profile_dir()}[/]"
                )
                console.print(Panel(panel_content, title=f"[bold #c084fc]📊 {i18n.t('desc_status')}[/]", border_style="#a855f7", box=box.ROUNDED))
            elif cmd == "pages":
                await run_pages(cdp_port, i18n=i18n, services=services, current_page_id=current_page_id)
                res_p = await services.call("browser_list_pages", {})
                pages = res_p.get("pages", [])
                if pages and not current_page_id:
                    current_page_id = pages[0]["page_id"]
                    current_url = pages[0]["url"]
            elif cmd == "select":
                if not args:
                    console.print(f"[yellow]Uso/Usage: /select <# ou page_id>[/]")
                    continue
                arg_val = args[0]
                res_p = await services.call("browser_list_pages", {})
                pages = res_p.get("pages", [])
                
                target_id = arg_val
                if arg_val.isdigit():
                    idx = int(arg_val) - 1
                    if 0 <= idx < len(pages):
                        target_id = pages[idx]["page_id"]
                    else:
                        console.print(f"[yellow]Número de aba inválido: {arg_val}. Total de abas: {len(pages)}[/]")
                        continue
                
                try:
                    await services.call("browser_select_page", {"page_id": target_id})
                    current_page_id = target_id
                    target_page = next((p for p in pages if p["page_id"] == target_id), None)
                    if target_page:
                        current_url = target_page["url"]
                    console.print(f"[bold green][+][/] {i18n.t('tab_selected')} ([bold cyan]{target_id}[/])")
                except Exception as exc:
                    console.print(f"[yellow]Aviso: {exc}[/]")
            elif cmd in ("new", "newtab", "tab"):
                target_url = args[0] if args else "about:blank"
                if target_url != "about:blank" and not target_url.startswith(("http://", "https://", "about:")):
                    target_url = "https://" + target_url
                try:
                    res = await services.call("browser_new_tab", {"url": target_url})
                    current_page_id = res.get("page_id")
                    current_url = res.get("url", target_url)
                    console.print(f"[bold green][+][/] Nova aba: [bold cyan]{current_page_id}[/] ([dim]{current_url}[/])")
                except Exception as exc:
                    console.print(f"[yellow]Erro ao abrir aba: {exc}[/]")
            elif cmd in ("close", "closetab"):
                target_page = args[0] if args else current_page_id
                try:
                    res = await services.call("browser_close_tab", {"page_id": target_page})
                    console.print(f"[bold green][✓][/] Aba fechada: [cyan]{res.get('closed_page_id')}[/]")
                    current_page_id = res.get("active_page_id")
                    current_url = "about:blank"
                except Exception as exc:
                    console.print(f"[yellow]Erro ao fechar aba: {exc}[/]")
            elif cmd in ("goto", "open"):
                if not args:
                    console.print(f"[yellow]Uso/Usage: /{cmd} <url>[/]")
                    continue
                url = args[0]
                if not url.startswith("http://") and not url.startswith("https://"):
                    url = "https://" + url
                
                console.print(f"[bold #a855f7][*][/] {i18n.t('navigating_to')} [cyan]{url}[/]...")
                try:
                    res_nav = await services.call("browser_navigate", {
                        "url": url,
                        "page_id": current_page_id,
                        "wait_until": "domcontentloaded",
                        "timeout_ms": 20000
                    })
                    current_page_id = res_nav.get("page_id", current_page_id)
                    current_url = res_nav.get("url", url)
                    console.print(f"[bold green][+][/] {i18n.t('nav_success')} [bold cyan]{current_url}[/]!")
                except Exception as exc:
                    console.print(f"[yellow]Aviso / Warning: {exc}[/]")
            elif cmd in ("scroll", "rolar"):
                direction = "down"
                amount = 500
                if args:
                    first = args[0].lower()
                    if first in ("up", "cima"):
                        direction = "up"
                        if len(args) > 1 and args[1].isdigit():
                            amount = int(args[1])
                    elif first in ("top", "topo"):
                        direction = "top"
                    elif first in ("bottom", "fim", "baixo"):
                        direction = "bottom"
                    elif first in ("down",):
                        direction = "down"
                        if len(args) > 1 and args[1].isdigit():
                            amount = int(args[1])
                    elif first.isdigit():
                        amount = int(first)
                
                try:
                    res_scr = await services.call("browser_scroll", {
                        "direction": direction,
                        "amount": amount,
                        "page_id": current_page_id
                    })
                    console.print(f"[bold green][+][/] {i18n.t('scroll_success', direction=direction)}")
                except Exception as exc:
                    console.print(f"[yellow]Aviso / Warning: {exc}[/]")
            elif cmd in ("snapshot", "snap"):
                await run_snapshot(cdp_port, i18n=i18n, page_id=current_page_id, limit=200, services=services)
            elif cmd == "click":
                if not args:
                    console.print(f"[yellow]Uso/Usage: /click <element_ref>[/]")
                    continue
                ref = args[0]
                snap = await services.call("browser_snapshot", {"page_id": current_page_id, "limit": 200})
                res_act = await services.call("browser_action", {
                    "action": "click",
                    "snapshot_id": snap["snapshot_id"],
                    "element_ref": ref,
                    "page_id": snap["page_id"],
                    "timeout_ms": 5000
                })
                console.print(f"[bold green][+][/] {i18n.t('click_success')} [bold cyan][{ref}][/]! ([dim]{res_act.get('duration_ms', 0)}ms[/])")
            elif cmd == "fill":
                if len(args) < 2:
                    console.print(f"[yellow]Uso/Usage: /fill <element_ref> <text>[/]")
                    continue
                ref = args[0]
                text = " ".join(args[1:])
                snap = await services.call("browser_snapshot", {"page_id": current_page_id, "limit": 200})
                res_act = await services.call("browser_action", {
                    "action": "fill",
                    "snapshot_id": snap["snapshot_id"],
                    "element_ref": ref,
                    "page_id": snap["page_id"],
                    "value": text,
                    "timeout_ms": 5000
                })
                console.print(f"[bold green][+][/] {i18n.t('fill_success')} '[bold #f8fafc]{text}[/]'! ([dim]{res_act.get('duration_ms', 0)}ms[/])")
            elif cmd == "traffic":
                limit = int(args[0]) if args and args[0].isdigit() else 20
                await run_traffic(cdp_port, i18n=i18n, page_id=current_page_id, limit=limit, services=services)
            elif cmd == "curl":
                if not args:
                    console.print(f"[yellow]Uso/Usage: /curl <request_id>[/]")
                    continue
                req_id = args[0]
                res_c = await services.call("network_curl", {"request_id": req_id, "shell": "powershell"})
                console.print(Panel(f"[bold #a855f7]{res_c.get('curl')}[/]", title=f"[bold #c084fc]{i18n.t('curl_title')}[/]", border_style="#a855f7", box=box.ROUNDED))
            elif cmd in ("read", "reader"):
                max_len = int(args[0]) if args and args[0].isdigit() else 50000
                await run_read(cdp_port, i18n=i18n, page_id=current_page_id, max_length=max_len, services=services)
            elif cmd in ("report", "relatorio"):
                await run_report(cdp_port, i18n=i18n, page_id=current_page_id, services=services)
            elif cmd in ("export", "export-report", "dashboard"):
                target_file = args[0] if args else None
                await run_export_report(
                    cdp_port,
                    i18n=i18n,
                    page_id=current_page_id,
                    output_path=target_file,
                    services=services,
                )
            elif cmd in ("memory", "mem"):
                dom = args[0] if args else None
                await run_domain_memory(cdp_port, i18n=i18n, domain=dom, services=services)
            elif cmd in ("wait-human", "challenge", "wait-challenge"):
                timeout = int(args[0]) if args and args[0].isdigit() else 120
                await run_wait_challenge(
                    cdp_port,
                    i18n=i18n,
                    page_id=current_page_id,
                    timeout_s=timeout,
                    services=services,
                )
            elif cmd in ("ai", "protocol"):
                run_protocol(i18n.lang)
            elif cmd == "audit":
                await run_audit(cdp_port, i18n=i18n, page_id=current_page_id, services=services)
            else:
                console.print(f"[yellow]{i18n.t('cmd_not_recognized')}: '{raw_cmd}'. Digite /help para comandos.[/]")
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        try:
            await services.close()
        except Exception:
            pass
        console.print(f"\n[bold #a855f7]{i18n.t('goodbye')}[/]")
