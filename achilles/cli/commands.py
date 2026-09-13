"""Comandos CLI e REPL Interativo do Achilles CDP Agent com i18n (PT/EN) e Perfil Persistente."""

import asyncio
import ctypes
import json
import os
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

console = Console(force_terminal=True, color_system="truecolor")

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
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Achilles" / "chrome_profile"
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

    possible_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    chrome_bin = next((p for p in possible_paths if os.path.exists(p)), None)
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
        i18n.t("cat_inspect"),
        "/snapshot (ou /snap)",
        i18n.t("desc_snap"),
        "/snapshot",
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
        i18n.t("cat_security"),
        "/audit",
        i18n.t("desc_audit"),
        "/audit",
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


async def run_pages(cdp_port: int, i18n: I18n, services=None) -> None:
    should_close = False
    if services is None:
        from achilles.services.application import ApplicationServices
        services = ApplicationServices(cdp_port)
        should_close = True

    try:
        res = await services.call("browser_list_pages", {})
        pages = res.get("pages", [])
        active_id = res.get("active_page_id")
        
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
        table.add_column("Status", width=12, justify="center")
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


async def run_snapshot(cdp_port: int, i18n: I18n, page_id: Optional[str] = None, limit: int = 200, services=None) -> None:
    should_close = False
    if services is None:
        from achilles.services.application import ApplicationServices
        services = ApplicationServices(cdp_port)
        should_close = True

    try:
        args: Dict[str, Any] = {"limit": limit}
        if page_id:
            args["page_id"] = page_id
        res = await services.call("browser_snapshot", args)
        elements = res.get("elements", [])

        table = Table(
            title=f"[bold #e9d5ff]{i18n.t('snap_title')} [dim]({len(elements)} {i18n.t('snap_elements_count')})[/][/]",
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
                await run_pages(cdp_port, i18n=i18n, services=services)
            elif cmd == "select":
                if not args:
                    console.print(f"[yellow]Uso/Usage: /select <page_id>[/]")
                    continue
                target_id = args[0]
                await services.call("browser_select_page", {"page_id": target_id})
                current_page_id = target_id
                console.print(f"[bold green][+][/] {i18n.t('tab_selected')} ([bold cyan]{target_id}[/])")
            elif cmd in ("goto", "open"):
                if not args:
                    console.print(f"[yellow]Uso/Usage: /{cmd} <url>[/]")
                    continue
                url = args[0]
                if not url.startswith("http://") and not url.startswith("https://"):
                    url = "https://" + url
                
                page_id_resolved, page_obj = await services.session.page(current_page_id)
                current_page_id = page_id_resolved
                current_url = url
                console.print(f"[bold #a855f7][*][/] {i18n.t('navigating_to')} [cyan]{url}[/]...")
                await page_obj.goto(url, wait_until="domcontentloaded")
                console.print(f"[bold green][+][/] {i18n.t('nav_success')} [bold cyan]{url}[/]!")
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
