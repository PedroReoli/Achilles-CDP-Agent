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
from rich.markup import escape
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


def ensure_chrome_running(cdp_port: int, i18n: Optional[I18n] = None):
    try:
        with socket.create_connection(("127.0.0.1", cdp_port), timeout=0.5):
            return None
    except Exception:
        pass

    i18n = i18n or I18n()
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
        
        proc = None
        if sys.platform == "win32":
            try:
                cli_args = f'"{chrome_bin}" --remote-debugging-port={cdp_port} "--user-data-dir={profile_dir}" --no-first-run --no-default-browser-check about:blank'
                powershell_cmd = f"Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{{CommandLine = '{cli_args}'}}"
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command", powershell_cmd],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    check=True,
                )
            except Exception:
                popen_kwargs = {
                    "stdout": subprocess.DEVNULL,
                    "stderr": subprocess.DEVNULL,
                    "stdin": subprocess.DEVNULL,
                    "close_fds": True,
                    "creationflags": (
                        getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                    ),
                }
                proc = subprocess.Popen([
                    chrome_bin,
                    f"--remote-debugging-port={cdp_port}",
                    f"--user-data-dir={str(profile_dir)}",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "about:blank",
                ], **popen_kwargs)
        else:
            popen_kwargs = {
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "stdin": subprocess.DEVNULL,
                "close_fds": True,
            }
            proc = subprocess.Popen([
                chrome_bin,
                f"--remote-debugging-port={cdp_port}",
                f"--user-data-dir={str(profile_dir)}",
                "--no-first-run",
                "--no-default-browser-check",
                "about:blank",
            ], **popen_kwargs)
        
        for _ in range(50):
            time.sleep(0.2)
            try:
                with socket.create_connection(("127.0.0.1", cdp_port), timeout=0.5):
                    break
            except Exception:
                pass
        return proc
    return None


async def run_open(cdp_port: int, url: str, page_id: Optional[str] = None, i18n: Optional[I18n] = None, services=None) -> None:
    if not url.startswith(("http://", "https://", "about:", "chrome://")):
        url = "https://" + url
    should_close = False
    i18n = i18n or I18n()
    if services is None:
        ensure_chrome_running(cdp_port, i18n)
        from achilles.services.application import ApplicationServices
        services = ApplicationServices(cdp_port)
        should_close = True

    try:
        args: Dict[str, Any] = {"url": url}
        if page_id:
            args["page_id"] = page_id
        console.print(f"[bold #a855f7][*][/] Navegando para [cyan]{url}[/]...")
        res = await services.call("browser_navigate", args)
        console.print(f"[bold green]✔ Concluído:[/] '{res.get('title')}' ([dim]{res.get('url')}[/])")
    finally:
        if should_close:
            await services.close()
            await asyncio.sleep(0.05)


async def run_status(cdp_port: int, i18n: Optional[I18n] = None, services=None) -> None:
    should_close = False
    i18n = i18n or I18n()
    if services is None:
        ensure_chrome_running(cdp_port, i18n)
        from achilles.services.application import ApplicationServices
        services = ApplicationServices(cdp_port)
        should_close = True

    try:
        if should_close:
            await services.call("browser_list_pages", {})
        status = await services.call("browser_status", {})
        panel_content = Text.from_markup(
            f"[bold #a855f7]CDP Endpoint:[/] [cyan]{status.get('cdp_url')}[/]\n"
            f"[bold #a855f7]Modo / Mode:[/] [green]{status.get('mode')}[/]\n"
            f"[bold #a855f7]Reqs Gravadas:[/] [bold #c084fc]{status.get('recorded_requests')}[/]\n"
            f"[bold #a855f7]Geração / Generation:[/] {status.get('generation')}\n"
            f"[bold #a855f7]Profile Dir:[/] [dim cyan]{get_chrome_profile_dir()}[/]"
        )
        console.print(Panel(panel_content, title=f"[bold #c084fc]📊 {i18n.t('desc_status')}[/]", border_style="#a855f7", box=box.ROUNDED))
    finally:
        if should_close:
            await services.close()
            await asyncio.sleep(0.05)


async def run_pages(cdp_port: int, i18n: I18n, services=None, current_page_id: Optional[str] = None) -> None:
    should_close = False
    if services is None:
        ensure_chrome_running(cdp_port, i18n)
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
        table.add_column("#", style="bold #c084fc", justify="center")
        table.add_column(i18n.t("col_status"), justify="center")
        table.add_column("Page ID", style="bold #e9d5ff")
        table.add_column("Título / Title", style="#f8fafc")
        table.add_column("URL", style="cyan")

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
            await asyncio.sleep(0.05)


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
        ensure_chrome_running(cdp_port, i18n)
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
            caption=f"[bold green]✔ Economia de Tokens: {saved_pct} (Viewport)[/]" if saved_pct else None,
            border_style="#a855f7",
            box=box.ROUNDED,
            header_style="bold #c084fc",
        )
        table.add_column(i18n.t("col_ref"), style="bold cyan")
        table.add_column(i18n.t("col_role"), style="bold #c084fc")
        table.add_column(i18n.t("col_name"), style="#f8fafc")
        table.add_column(i18n.t("col_state"), justify="center")

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

            table.add_row(escape(f"[{ref}]"), role_badge, escape(str(name)[:44]), state)

        console.print(table)
    finally:
        if should_close:
            await services.close()
            await asyncio.sleep(0.05)


async def run_act(
    cdp_port: int,
    action: str,
    element_ref: str,
    value: Optional[str] = None,
    page_id: Optional[str] = None,
    i18n: Optional[I18n] = None,
    services=None,
) -> None:
    should_close = False
    i18n = i18n or I18n()
    if services is None:
        ensure_chrome_running(cdp_port, i18n)
        from achilles.services.application import ApplicationServices
        services = ApplicationServices(cdp_port)
        should_close = True

    try:
        clean_ref = element_ref.strip("[]@")

        if action in ("scroll", "rolar"):
            direction = clean_ref.lower() if clean_ref in ("down", "up", "top", "bottom", "baixo", "cima", "topo", "fim") else "down"
            amount = int(value) if value and value.isdigit() else 500
            res = await services.call("browser_scroll", {
                "direction": direction,
                "amount": amount,
                "page_id": page_id,
            })
            console.print(f"[bold green][✓] {i18n.t('scroll_success', direction=direction)}[/]")
            return

        # Snapshot first to register elements and acquire locator context
        snap = await services.call("browser_snapshot", {"page_id": page_id, "limit": 200, "in_viewport_only": False})
        active_page_id = snap.get("page_id")

        # Smart element resolution: match exact ref, suffix (_N), 1-based index (N), or label name
        matching_el = next((e for e in snap.get("elements", []) if e.get("element_ref") == clean_ref), None)
        if not matching_el:
            matching_el = next((e for e in snap.get("elements", []) if e.get("element_ref", "").endswith(f"_{clean_ref}")), None)
        if not matching_el and clean_ref.isdigit():
            idx = int(clean_ref) - 1
            elements = snap.get("elements", [])
            if 0 <= idx < len(elements):
                matching_el = elements[idx]
        if not matching_el:
            matching_el = next((e for e in snap.get("elements", []) if clean_ref.lower() in (e.get("name") or "").lower()), None)

        if matching_el:
            clean_ref = matching_el["element_ref"]

        action_args: Dict[str, Any] = {
            "action": action,
            "snapshot_id": snap["snapshot_id"],
            "element_ref": clean_ref,
            "page_id": active_page_id,
            "timeout_ms": 5000,
        }
        if value is not None:
            action_args["value"] = value

        console.print(f"[bold #a855f7][*][/] Executando [bold cyan]{action}[/] em [cyan]{clean_ref}[/]...")
        res = await services.call("browser_action", action_args)
        duration = res.get("duration_ms", 0)
        console.print(f"[bold green][✓] Sucesso:[/] Ação '{action}' executada em {duration}ms!")
    except Exception as exc:
        console.print(f"[bold red]❌ Falha ao executar ação:[/] {exc}")
        raise SystemExit(1) from None
    finally:
        if should_close:
            await services.close()
            await asyncio.sleep(0.05)


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
            await asyncio.sleep(0.05)


async def run_curl(cdp_port: int, request_id: str, shell: str = "powershell", i18n: Optional[I18n] = None, services=None) -> None:
    should_close = False
    i18n = i18n or I18n()
    if services is None:
        ensure_chrome_running(cdp_port, i18n)
        from achilles.services.application import ApplicationServices
        services = ApplicationServices(cdp_port)
        should_close = True

    try:
        res = await services.call("network_curl", {"request_id": request_id, "shell": shell})
        curl_cmd = res.get("curl", "")
        console.print(Panel(f"[bold #a855f7]{curl_cmd}[/]", title=f"[bold #c084fc]{i18n.t('curl_title')}[/]", border_style="#a855f7", box=box.ROUNDED))
    except Exception as exc:
        console.print(f"[bold red]❌ Falha ao gerar cURL:[/] {exc}")
        raise SystemExit(1) from None
    finally:
        if should_close:
            await services.close()
            await asyncio.sleep(0.05)


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

        # Browser posture panel
        stealth_info = (
            "[bold green]✔ Navegador real conectado por CDP[/] (Chrome, Chromium ou Edge)\n"
            "[bold green]✔ Sinais básicos de automação reduzidos[/] (sem promessa de invisibilidade)\n"
            "[bold green]✔ Fingerprint nativo preservado[/] (hardware, Canvas, WebGL e áudio coerentes)\n"
            "[bold green]✔ Native Title Bar HUD[/] (Fora do DOM/HTML, ancorado ao lado do minimizar do Windows)\n"
            "[bold green]✔ Perfil Persistente de Usuário Ativo[/] (Cookies, logins e sessões preservados)\n"
            "[bold green]✔ Handshake humano para desafios[/] (CAPTCHA e 2FA detectados e aguardados)\n"
            "[bold green]✔ Redação Zero-Secret Ativa[/] (Senhas, Bearer tokens e chaves mascarados)"
        )
        console.print(Panel(stealth_info, title="[bold #c084fc]🛡️ Postura do Navegador e Segurança[/]", border_style="green", box=box.ROUNDED))
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
        console.print("[bold yellow][!][/] [bold #e9d5ff]Monitorando desafios anti-bot / 2FA / Login...[/]")
        console.print("[dim #94a3b8]    Se houver CAPTCHA ou login na janela do Chrome, resolva diretamente no navegador.[/]")
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
    from achilles.cli.interactive import run_protocol as implementation

    implementation(lang)


async def run_interactive(cdp_port: int, lang: Optional[str] = None) -> None:
    from achilles.cli.interactive import run_interactive as implementation

    await implementation(cdp_port, lang)
