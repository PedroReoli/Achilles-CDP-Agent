"""Comandos CLI e REPL Interativo do Achilles CDP Agent com Rich Purple Theme."""

import asyncio
import ctypes
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
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

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

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


def _print_banner():
    console.print(f"[bold #c084fc]{ASCII_BANNER}[/]")
    console.print("      [bold #e9d5ff]Achilles CDP Agent[/] [dim #a855f7]—[/] [dim #cbd5e1]Autonomous Browser Automation & Security[/]\n")


def ensure_chrome_running(cdp_port: int):
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
        console.print(f"[yellow][*][/] Chrome CDP não detectado na porta {cdp_port}.")
        console.print(f"[bold #a855f7][*][/] Iniciando Google Chrome com depuração na porta {cdp_port}...")
        pdir = os.path.join(tempfile.gettempdir(), f"achilles_profile_{cdp_port}")
        proc = subprocess.Popen([
            chrome_bin,
            f"--remote-debugging-port={cdp_port}",
            f"--user-data-dir={pdir}",
            "--no-first-run",
            "--no-default-browser-check",
            "about:blank"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        for _ in range(25):
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


async def run_status(cdp_port: int) -> None:
    from achilles.services.application import ApplicationServices
    services = ApplicationServices(cdp_port)
    try:
        status = await services.call("browser_status", {})
        console.print(f"\n[bold #c084fc]--- [ACHILLES CDP STATUS] ---[/]")
        console.print(f"[bold #a855f7]CDP URL:[/]          {status.get('cdp_url')}")
        console.print(f"[bold #a855f7]Modo:[/]             {status.get('mode')}")
        console.print(f"[bold #a855f7]Geração:[/]          {status.get('generation')}")
        console.print(f"[bold #a855f7]Reqs Gravadas:[/]    {status.get('recorded_requests')}")
        console.print(f"[bold #a855f7]Eventos Dropados:[/] {status.get('dropped_events')}")
    finally:
        await services.close()


async def run_pages(cdp_port: int) -> None:
    from achilles.services.application import ApplicationServices
    services = ApplicationServices(cdp_port)
    try:
        res = await services.call("browser_list_pages", {})
        pages = res.get("pages", [])
        active_id = res.get("active_page_id")
        console.print(f"\n[bold #c084fc]--- [ABAS DO NAVEGADOR ({len(pages)})] ---[/]")
        if not pages:
            console.print("[yellow]Nenhuma aba detectada. Digite '/open https://site.com' para abrir uma.[/]")
            return
        for idx, p in enumerate(pages, start=1):
            is_active = " [bold green][ATIVA][/]" if p.get("page_id") == active_id else ""
            console.print(f"[bold #a855f7][{idx}][/] ID: [bold #e9d5ff]{p['page_id']}[/]{is_active}")
            console.print(f"    Título: {p.get('title', '(Sem título)')}")
            console.print(f"    URL:    [cyan]{p.get('url', 'about:blank')}[/]")
    finally:
        await services.close()


async def run_snapshot(cdp_port: int, page_id: Optional[str] = None, limit: int = 200) -> None:
    from achilles.services.application import ApplicationServices
    services = ApplicationServices(cdp_port)
    try:
        args: Dict[str, Any] = {"limit": limit}
        if page_id:
            args["page_id"] = page_id
        res = await services.call("browser_snapshot", args)
        elements = res.get("elements", [])
        console.print(f"\n[bold #c084fc]--- [SNAPSHOT SEMÂNTICO (ID: {res.get('snapshot_id')})] ---[/]")
        console.print(f"[dim]Página: {res.get('page_id')} | Total Elementos: {len(elements)}[/]\n")
        console.print("[bold #a855f7][Elementos Interativos]:[/]")
        for line in res.get("compact", "").split("\n"):
            if line.strip():
                console.print(f"  [cyan]{line}[/]")
    finally:
        await services.close()


async def run_act(cdp_port: int, action: str, element_ref: str, value: Optional[str] = None, page_id: Optional[str] = None) -> None:
    from achilles.services.application import ApplicationServices
    services = ApplicationServices(cdp_port)
    try:
        args_snap: Dict[str, Any] = {"limit": 200}
        if page_id:
            args_snap["page_id"] = page_id
        snap = await services.call("browser_snapshot", args_snap)
        
        args_act: Dict[str, Any] = {
            "action": action,
            "snapshot_id": snap["snapshot_id"],
            "element_ref": element_ref,
            "page_id": snap["page_id"],
            "timeout_ms": 5000
        }
        if value is not None:
            args_act["value"] = value

        console.print(f"\n[bold #a855f7][*][/] Executando '{action}' em [{element_ref}] na página {snap['page_id']}...")
        res = await services.call("browser_action", args_act)
        console.print(f"[bold green][+][/] Status: {res.get('status')} | Duração: {res.get('duration_ms', 0)}ms")
    finally:
        await services.close()


async def run_traffic(cdp_port: int, page_id: Optional[str] = None, limit: int = 50) -> None:
    from achilles.services.application import ApplicationServices
    services = ApplicationServices(cdp_port)
    try:
        args: Dict[str, Any] = {"limit": limit}
        if page_id:
            args["page_id"] = page_id
        res = await services.call("network_query", args)
        records = res.get("records", [])
        console.print(f"\n[bold #c084fc]--- [HISTÓRICO DE TRÁFEGO ({len(records)} itens)] ---[/]")
        for r in records:
            status = r.get("status") or "PEND"
            status_color = "green" if str(status).startswith("2") else ("yellow" if str(status).startswith("3") else "magenta")
            console.print(f"[{r.get('request_id')}] [{r.get('method')}] [cyan]{r.get('url')}[/] (Status: [{status_color}]{status}[/], {r.get('duration_ms', 0)}ms)")
    finally:
        await services.close()


async def run_curl(cdp_port: int, request_id: str, shell: str = "powershell") -> None:
    from achilles.services.application import ApplicationServices
    services = ApplicationServices(cdp_port)
    try:
        res = await services.call("network_curl", {"request_id": request_id, "shell": shell})
        console.print(f"\n[bold #c084fc]--- [CURL EXPORT ({shell.upper()})] ---[/]")
        console.print(f"[bold #a855f7]{res.get('curl')}[/]")
    finally:
        await services.close()


async def run_audit(cdp_port: int, page_id: Optional[str] = None) -> None:
    from achilles.services.application import ApplicationServices
    services = ApplicationServices(cdp_port)
    try:
        args: Dict[str, Any] = {}
        if page_id:
            args["page_id"] = page_id
        res = await services.call("security_audit", args)
        score = res.get("security_score")
        score_str = f"{score}/100" if score is not None else "N/A"
        console.print(f"\n[bold #c084fc]--- [AUDITORIA DE SEGURANÇA OWASP (Score: {score_str})] ---[/]")
        console.print(f"[dim]URL: {res.get('url')}[/]")
        findings = res.get("findings", [])
        console.print(f"Total de Achados: {len(findings)}\n")
        for f in findings:
            sev = f.get('severity', 'info').upper()
            sev_color = "yellow" if sev in ("HIGH", "CRITICAL") else ("cyan" if sev == "MEDIUM" else "dim")
            console.print(f"  • [{sev_color}][{sev}][/{sev_color}] [bold #e9d5ff]{f.get('title')}[/]")
            if f.get('description'):
                console.print(f"    [dim]Descrição:[/] {f.get('description')}")
            if f.get('remediation'):
                console.print(f"    [bold green]Correção:[/]  {f.get('remediation')}")
    finally:
        await services.close()


async def run_interactive(cdp_port: int) -> None:
    from achilles.services.application import ApplicationServices
    _print_banner()
    ensure_chrome_running(cdp_port)
    console.print(f"[bold #a855f7]Conectando ao Chrome CDP na porta {cdp_port}...[/]")
    
    services = ApplicationServices(cdp_port)
    current_page_id: Optional[str] = None
    latest_snapshot: Optional[Dict[str, Any]] = None

    try:
        res_pages = await services.call("browser_list_pages", {})
        pages = res_pages.get("pages", [])
        if pages:
            current_page_id = res_pages.get("active_page_id") or pages[0]["page_id"]
        else:
            try:
                page_id, page_obj = await services.session.page()
                current_page_id = page_id
            except Exception:
                pass
    except Exception:
        pass

    console.print(f"\n[bold green][✓][/] [bold #e9d5ff]Modo Interativo do Achilles iniciado![/]")
    console.print(f"[dim #cbd5e1]    Digite [bold #c084fc]/help[/] para ver os comandos ou [bold #c084fc]/exit[/] para sair.[/]\n")

    try:
        while True:
            try:
                prompt_label = f"achilles ({current_page_id or 'sem aba'})> "
                console.print(f"[bold #a855f7]achilles[/] ([cyan]{current_page_id or 'sem aba'}[/])[bold #c084fc]>[/] ", end="")
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
                console.print(f"""
[bold #c084fc]Comandos Disponíveis (Use com ou sem '/'):[/]
  [bold #a855f7]/pages[/]                     Lista todas as abas abertas no navegador
  [bold #a855f7]/open <url>[/]                Abre uma nova aba com a URL indicada
  [bold #a855f7]/goto <url>[/]                Navega a aba atual para uma URL
  [bold #a855f7]/select <page_id>[/]          Seleciona e foca uma aba específica
  [bold #a855f7]/snapshot[/] (ou /snap)        Captura a árvore de elementos interativos
  [bold #a855f7]/click <ref>[/]                Clica em um elemento pelo [ref] do snapshot
  [bold #a855f7]/fill <ref> <texto>[/]         Digita texto em um campo pelo [ref]
  [bold #a855f7]/traffic [limit][/]            Lista o histórico de requisições de rede
  [bold #a855f7]/curl <req_id>[/]              Gera o comando cURL seguro da requisição
  [bold #a855f7]/audit[/]                      Executa auditoria de postura de segurança OWASP
  [bold #a855f7]/status[/]                     Mostra o status da conexão CDP e métricas
  [bold #a855f7]/clear[/]                      Limpa a tela do terminal
  [bold #a855f7]/exit[/]                       Encerra o modo interativo
""")
            elif cmd == "clear":
                os.system("cls" if os.name == "nt" else "clear")
            elif cmd == "status":
                status = await services.call("browser_status", {})
                console.print(f"[bold #c084fc][STATUS][/] CDP: {status.get('cdp_url')} | Generation: {status.get('generation')} | Reqs: {status.get('recorded_requests')}")
            elif cmd == "pages":
                res = await services.call("browser_list_pages", {})
                pages = res.get("pages", [])
                console.print(f"[bold #c084fc]Abas abertas ({len(pages)}):[/]")
                for p in pages:
                    mark = " [bold green]*[/]" if p["page_id"] == current_page_id else ""
                    console.print(f"  [[bold #a855f7]{p['page_id']}[/]]{mark} {p.get('title', '')} -> [cyan]{p.get('url')}[/]")
                if pages and not current_page_id:
                    current_page_id = pages[0]["page_id"]
                    console.print(f"[bold #a855f7][*][/] Aba ativa definida para: {current_page_id}")
            elif cmd == "select":
                if not args:
                    console.print("[yellow]Uso: /select <page_id>[/]")
                    continue
                target_id = args[0]
                await services.call("browser_select_page", {"page_id": target_id})
                current_page_id = target_id
                console.print(f"[bold green][+][/] Aba {target_id} selecionada!")
            elif cmd in ("goto", "open"):
                if not args:
                    console.print(f"[yellow]Uso: /{cmd} <url>[/]")
                    continue
                url = args[0]
                if not url.startswith("http://") and not url.startswith("https://"):
                    url = "https://" + url
                
                page_id_resolved, page_obj = await services.session.page(current_page_id)
                current_page_id = page_id_resolved
                console.print(f"[bold #a855f7][*][/] Navegando para [cyan]{url}[/]...")
                await page_obj.goto(url, wait_until="domcontentloaded")
                console.print("[bold green][+][/] Navegação concluída!")
            elif cmd in ("snapshot", "snap"):
                res_snap = await services.call("browser_snapshot", {"page_id": current_page_id, "limit": 200})
                latest_snapshot = res_snap
                current_page_id = res_snap["page_id"]
                elements = res_snap.get('elements', [])
                console.print(f"\n[bold #c084fc][SNAPSHOT {res_snap['snapshot_id']}][/] [dim]({len(elements)} elementos)[/]")
                for line in res_snap.get("compact", "").split("\n"):
                    if line.strip():
                        console.print(f"  [cyan]{line}[/]")
            elif cmd == "click":
                if not args:
                    console.print("[yellow]Uso: /click <element_ref>[/]")
                    continue
                if not latest_snapshot:
                    latest_snapshot = await services.call("browser_snapshot", {"page_id": current_page_id, "limit": 200})
                ref = args[0]
                res_act = await services.call("browser_action", {
                    "action": "click",
                    "snapshot_id": latest_snapshot["snapshot_id"],
                    "element_ref": ref,
                    "page_id": latest_snapshot["page_id"],
                    "timeout_ms": 5000
                })
                console.print(f"[bold green][+][/] Clique em [{ref}]: {res_act.get('status')}")
            elif cmd == "fill":
                if len(args) < 2:
                    console.print("[yellow]Uso: /fill <element_ref> <texto>[/]")
                    continue
                if not latest_snapshot:
                    latest_snapshot = await services.call("browser_snapshot", {"page_id": current_page_id, "limit": 200})
                ref = args[0]
                text = " ".join(args[1:])
                res_act = await services.call("browser_action", {
                    "action": "fill",
                    "snapshot_id": latest_snapshot["snapshot_id"],
                    "element_ref": ref,
                    "page_id": latest_snapshot["page_id"],
                    "value": text,
                    "timeout_ms": 5000
                })
                console.print(f"[bold green][+][/] Preenchimento de [{ref}] com '{text}': {res_act.get('status')}")
            elif cmd == "traffic":
                limit = int(args[0]) if args and args[0].isdigit() else 20
                res_tr = await services.call("network_query", {"page_id": current_page_id, "limit": limit})
                records = res_tr.get("records", [])
                console.print(f"[bold #c084fc]Tráfego ({len(records)} requisições):[/]")
                for r in records:
                    st = r.get('status') or 'PEND'
                    st_c = "green" if str(st).startswith('2') else ("yellow" if str(st).startswith('3') else "magenta")
                    console.print(f"  [[bold #a855f7]{r['request_id']}[/]] [{r['method']}] [cyan]{r['url']}[/] (Status: [{st_c}]{st}[/])")
            elif cmd == "curl":
                if not args:
                    console.print("[yellow]Uso: /curl <request_id>[/]")
                    continue
                req_id = args[0]
                res_c = await services.call("network_curl", {"request_id": req_id, "shell": "powershell"})
                console.print(f"[bold #c084fc]cURL Export:[/]\n[bold #a855f7]{res_c.get('curl')}[/]")
            elif cmd == "audit":
                res_aud = await services.call("security_audit", {"page_id": current_page_id})
                score = res_aud.get("security_score")
                console.print(f"\n[bold #c084fc][AUDITORIA][/] Score: [bold green]{score}/100[/] | URL: [cyan]{res_aud.get('url')}[/]")
                for f in res_aud.get("findings", []):
                    sev = f.get('severity', 'info').upper()
                    console.print(f"  • [{sev}] [bold #e9d5ff]{f.get('title')}[/]: {f.get('description')}")
            else:
                console.print(f"[yellow]Comando não reconhecido: '{raw_cmd}'. Digite /help para ver os comandos.[/]")
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        try:
            await services.close()
        except Exception:
            pass
        console.print(f"\n[bold #a855f7]Achilles encerrado com sucesso. Até logo![/]")
