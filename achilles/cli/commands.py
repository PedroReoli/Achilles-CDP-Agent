"""Comandos CLI e REPL Interativo do Achilles CDP Agent com Tema Roxo e Suporte a Slash Commands."""

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from typing import Any, Dict, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
        # Habilitar ANSI no Windows CMD
        os.system("")
    except Exception:
        pass

# Paleta de Cores Reoli / Purple Theme
P_BOLD = "\033[1;38;2;192;132;252m"   # Roxo Claro Brilhante
P_MAIN = "\033[38;2;168;85;247m"     # Roxo Principal Reoli
P_DARK = "\033[38;2;126;34;206m"     # Roxo Escuro
CYAN = "\033[38;2;56;189;248m"        # Ciano
GREEN = "\033[38;2;74;222;128m"      # Verde Sucesso
YELLOW = "\033[38;2;250;204;21m"     # Amarelo Alerta
GRAY = "\033[38;2;156;163;175m"       # Cinza / Dim
RESET = "\033[0m"                     # Reset


def _print_banner():
    banner = f"""{P_MAIN}
 ▄▄▄       ▄████▄   ██░ ██  ██▓ ██▓     ██▓    ▓█████   ██████ 
▒████▄    ▒██▀ ▀█  ▓██░ ██▒▓██▒▓██▒    ▓██▒    ▓█   ▀ ▒██    ▒ 
▒██  ▀█▄  ▒▓█    ▄ ▒██▀▀██░▒██▒▒██░    ▒██░    ▒███   ░ ▓██▄   
░██▄▄▄▄██ ▒▓▓▄ ▄██▒░▓█ ░██ ░██░▒██░    ▒██░    ▒▓█  ▄   ▒   ██▒
 ▓█   ▓██▒▒ ▓███▀ ░░▓█▒░██▓░██░░██████▒░██████▒░▒████▒▒██████▒▒
 ▒▒   ▓▒█░░ ░▒ ▒  ░ ▒ ░░▒░▒░▓  ░ ▒░▓  ░░ ▒░▓  ░░░ ▒░ ░▒ ▒▓▒ ▒ ░
  ▒   ▒▒ ░  ░  ▒    ▒ ░▒░ ░ ▒ ░░ ░ ▒  ░░ ░ ▒  ░ ░ ░  ░░ ░▒  ░ ░
  ░   ▒   ░         ░  ░░ ░ ▒ ░  ░ ░     ░ ░        ░  ░  ░  ░  
      ░  ░░ ░       ░  ░  ░ ░      ░  ░    ░  ░     ░        ░  
          ░                                                     {RESET}
      {P_BOLD}Achilles CDP Agent{RESET} — {GRAY}Autonomous Browser Automation & Security{RESET}
"""
    print(banner)


def ensure_chrome_running(cdp_port: int):
    import tempfile
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
        print(f"{YELLOW}[*]{RESET} Chrome CDP não detectado na porta {cdp_port}.")
        print(f"{P_MAIN}[*]{RESET} Iniciando Google Chrome com depuração na porta {cdp_port}...")
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
        print(f"\n{P_BOLD}--- [ACHILLES CDP STATUS] ---{RESET}")
        print(f"{P_MAIN}CDP URL:{RESET}          {status.get('cdp_url')}")
        print(f"{P_MAIN}Modo:{RESET}             {status.get('mode')}")
        print(f"{P_MAIN}Geração:{RESET}          {status.get('generation')}")
        print(f"{P_MAIN}Reqs Gravadas:{RESET}    {status.get('recorded_requests')}")
        print(f"{P_MAIN}Eventos Dropados:{RESET} {status.get('dropped_events')}")
    finally:
        await services.close()


async def run_pages(cdp_port: int) -> None:
    from achilles.services.application import ApplicationServices
    services = ApplicationServices(cdp_port)
    try:
        res = await services.call("browser_list_pages", {})
        pages = res.get("pages", [])
        active_id = res.get("active_page_id")
        print(f"\n{P_BOLD}--- [ABAS DO NAVEGADOR ({len(pages)})] ---{RESET}")
        if not pages:
            print(f"{YELLOW}Nenhuma aba detectada. Digite '/open https://site.com' para abrir uma.{RESET}")
            return
        for idx, p in enumerate(pages, start=1):
            is_active = f" {GREEN}[ATIVA]{RESET}" if p.get("page_id") == active_id else ""
            print(f"{P_MAIN}[{idx}]{RESET} ID: {P_BOLD}{p['page_id']}{RESET}{is_active}")
            print(f"    Título: {p.get('title', '(Sem título)')}")
            print(f"    URL:    {CYAN}{p.get('url', 'about:blank')}{RESET}")
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
        print(f"\n{P_BOLD}--- [SNAPSHOT SEMÂNTICO (ID: {res.get('snapshot_id')})] ---{RESET}")
        print(f"{GRAY}Página: {res.get('page_id')} | Total Elementos: {len(res.get('elements', []))}{RESET}")
        print(f"\n{P_MAIN}[Elementos Interativos]:{RESET}")
        for line in res.get("compact", "").split("\n"):
            if line.strip():
                print(f"  {CYAN}{line}{RESET}")
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

        print(f"\n{P_MAIN}[*]{RESET} Executando '{action}' em [{element_ref}] na página {snap['page_id']}...")
        res = await services.call("browser_action", args_act)
        print(f"{GREEN}[+]{RESET} Status: {res.get('status')} | Duração: {res.get('duration_ms', 0)}ms")
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
        print(f"\n{P_BOLD}--- [HISTÓRICO DE TRÁFEGO ({len(records)} itens)] ---{RESET}")
        for r in records:
            status = r.get("status") or "PEND"
            status_color = GREEN if str(status).startswith("2") else (YELLOW if str(status).startswith("3") else P_MAIN)
            print(f"[{r.get('request_id')}] [{r.get('method')}] {CYAN}{r.get('url')}{RESET} (Status: {status_color}{status}{RESET}, {r.get('duration_ms', 0)}ms)")
    finally:
        await services.close()


async def run_curl(cdp_port: int, request_id: str, shell: str = "powershell") -> None:
    from achilles.services.application import ApplicationServices
    services = ApplicationServices(cdp_port)
    try:
        res = await services.call("network_curl", {"request_id": request_id, "shell": shell})
        print(f"\n{P_BOLD}--- [CURL EXPORT ({shell.upper()})] ---{RESET}")
        print(f"{P_MAIN}{res.get('curl')}{RESET}")
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
        print(f"\n{P_BOLD}--- [AUDITORIA DE SEGURANÇA OWASP (Score: {score_str})] ---{RESET}")
        print(f"{GRAY}URL: {res.get('url')}{RESET}")
        findings = res.get("findings", [])
        print(f"Total de Achados: {len(findings)}\n")
        for f in findings:
            sev = f.get('severity', 'info').upper()
            sev_color = YELLOW if sev in ("HIGH", "CRITICAL") else (CYAN if sev == "MEDIUM" else GRAY)
            print(f"  • {sev_color}[{sev}]{RESET} {P_BOLD}{f.get('title')}{RESET}")
            if f.get('description'):
                print(f"    {GRAY}Descrição:{RESET} {f.get('description')}")
            if f.get('remediation'):
                print(f"    {GREEN}Correção:{RESET}  {f.get('remediation')}")
    finally:
        await services.close()


async def run_interactive(cdp_port: int) -> None:
    from achilles.services.application import ApplicationServices
    _print_banner()
    ensure_chrome_running(cdp_port)
    print(f"{P_MAIN}Conectando ao Chrome CDP na porta {cdp_port}...{RESET}")
    
    services = ApplicationServices(cdp_port)
    current_page_id: Optional[str] = None
    latest_snapshot: Optional[Dict[str, Any]] = None

    # Tenta detectar abas abertas de imediato
    try:
        res_pages = await services.call("browser_list_pages", {})
        pages = res_pages.get("pages", [])
        if pages:
            current_page_id = res_pages.get("active_page_id") or pages[0]["page_id"]
        else:
            # Abre uma aba inicial automaticamente se não houver nenhuma
            try:
                page_id, page_obj = await services.session.page()
                current_page_id = page_id
            except Exception:
                pass
    except Exception:
        pass

    print(f"\n{GREEN}[✓]{RESET} {P_BOLD}Modo Interativo do Achilles iniciado!{RESET}")
    print(f"{GRAY}    Digite {P_BOLD}/help{RESET}{GRAY} para ver os comandos ou {P_BOLD}/exit{RESET}{GRAY} para sair.{RESET}\n")

    try:
        while True:
            try:
                prompt_label = f"{P_MAIN}achilles{RESET} ({CYAN}{current_page_id or 'sem aba'}{RESET}){P_BOLD}>{RESET} "
                raw = await asyncio.to_thread(input, prompt_label)
            except (EOFError, KeyboardInterrupt):
                break
            
            line = raw.strip()
            if not line:
                continue
            
            parts = line.split()
            # Suporta comando com ou sem barra (ex: /help ou help, /pages ou pages)
            raw_cmd = parts[0].lower()
            cmd = raw_cmd[1:] if raw_cmd.startswith("/") else raw_cmd
            args = parts[1:]

            if cmd in ("exit", "quit", "q"):
                break
            elif cmd in ("help", "h", "?"):
                print(f"""
{P_BOLD}Comandos Disponíveis (Use com ou sem '/'):{RESET}
  {P_MAIN}/pages{RESET}                     Lista todas as abas abertas no navegador
  {P_MAIN}/open <url>{RESET}                Abre uma nova aba com a URL indicada
  {P_MAIN}/goto <url>{RESET}                Navega a aba atual para uma URL
  {P_MAIN}/select <page_id>{RESET}          Seleciona e foca uma aba específica
  {P_MAIN}/snapshot{RESET} (ou /snap)        Captura a árvore de elementos interativos
  {P_MAIN}/click <ref>{RESET}                Clica em um elemento pelo [ref] do snapshot
  {P_MAIN}/fill <ref> <texto>{RESET}         Digita texto em um campo pelo [ref]
  {P_MAIN}/traffic [limit]{RESET}            Lista o histórico de requisições de rede
  {P_MAIN}/curl <req_id>{RESET}              Gera o comando cURL seguro da requisição
  {P_MAIN}/audit{RESET}                      Executa auditoria de postura de segurança OWASP
  {P_MAIN}/status{RESET}                     Mostra o status da conexão CDP e métricas
  {P_MAIN}/clear{RESET}                      Limpa a tela do terminal
  {P_MAIN}/exit{RESET}                       Encerra o modo interativo
""")
            elif cmd == "clear":
                os.system("cls" if os.name == "nt" else "clear")
            elif cmd == "status":
                status = await services.call("browser_status", {})
                print(f"{P_BOLD}[STATUS]{RESET} CDP: {status.get('cdp_url')} | Generation: {status.get('generation')} | Reqs: {status.get('recorded_requests')}")
            elif cmd == "pages":
                res = await services.call("browser_list_pages", {})
                pages = res.get("pages", [])
                print(f"{P_BOLD}Abas abertas ({len(pages)}):{RESET}")
                for p in pages:
                    mark = f" {GREEN}*{RESET}" if p["page_id"] == current_page_id else ""
                    print(f"  [{P_MAIN}{p['page_id']}{RESET}]{mark} {p.get('title', '')} -> {CYAN}{p.get('url')}{RESET}")
                if pages and not current_page_id:
                    current_page_id = pages[0]["page_id"]
                    print(f"{P_MAIN}[*]{RESET} Aba ativa definida para: {current_page_id}")
            elif cmd == "select":
                if not args:
                    print(f"{YELLOW}Uso: /select <page_id>{RESET}")
                    continue
                target_id = args[0]
                await services.call("browser_select_page", {"page_id": target_id})
                current_page_id = target_id
                print(f"{GREEN}[+]{RESET} Aba {target_id} selecionada!")
            elif cmd in ("goto", "open"):
                if not args:
                    print(f"{YELLOW}Uso: /{cmd} <url>{RESET}")
                    continue
                url = args[0]
                if not url.startswith("http://") and not url.startswith("https://"):
                    url = "https://" + url
                
                # Se não há aba, obtém ou cria uma
                page_id_resolved, page_obj = await services.session.page(current_page_id)
                current_page_id = page_id_resolved
                print(f"{P_MAIN}[*]{RESET} Navegando para {CYAN}{url}{RESET}...")
                await page_obj.goto(url, wait_until="domcontentloaded")
                print(f"{GREEN}[+]{RESET} Navegação concluída!")
            elif cmd in ("snapshot", "snap"):
                res_snap = await services.call("browser_snapshot", {"page_id": current_page_id, "limit": 200})
                latest_snapshot = res_snap
                current_page_id = res_snap["page_id"]
                elements = res_snap.get('elements', [])
                print(f"\n{P_BOLD}[SNAPSHOT {res_snap['snapshot_id']}]{RESET} {GRAY}({len(elements)} elementos){RESET}")
                for line in res_snap.get("compact", "").split("\n"):
                    if line.strip():
                        print(f"  {CYAN}{line}{RESET}")
            elif cmd == "click":
                if not args:
                    print(f"{YELLOW}Uso: /click <element_ref>{RESET}")
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
                print(f"{GREEN}[+]{RESET} Clique em [{ref}]: {res_act.get('status')}")
            elif cmd == "fill":
                if len(args) < 2:
                    print(f"{YELLOW}Uso: /fill <element_ref> <texto>{RESET}")
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
                print(f"{GREEN}[+]{RESET} Preenchimento de [{ref}] com '{text}': {res_act.get('status')}")
            elif cmd == "traffic":
                limit = int(args[0]) if args and args[0].isdigit() else 20
                res_tr = await services.call("network_query", {"page_id": current_page_id, "limit": limit})
                records = res_tr.get("records", [])
                print(f"{P_BOLD}Tráfego ({len(records)} requisições):{RESET}")
                for r in records:
                    st = r.get('status') or 'PEND'
                    st_c = GREEN if str(st).startswith('2') else (YELLOW if str(st).startswith('3') else P_MAIN)
                    print(f"  [{P_MAIN}{r['request_id']}{RESET}] [{r['method']}] {CYAN}{r['url']}{RESET} (Status: {st_c}{st}{RESET})")
            elif cmd == "curl":
                if not args:
                    print(f"{YELLOW}Uso: /curl <request_id>{RESET}")
                    continue
                req_id = args[0]
                res_c = await services.call("network_curl", {"request_id": req_id, "shell": "powershell"})
                print(f"{P_BOLD}cURL Export:{RESET}\n{P_MAIN}{res_c.get('curl')}{RESET}")
            elif cmd == "audit":
                res_aud = await services.call("security_audit", {"page_id": current_page_id})
                score = res_aud.get("security_score")
                print(f"\n{P_BOLD}[AUDITORIA]{RESET} Score: {GREEN}{score}/100{RESET} | URL: {CYAN}{res_aud.get('url')}{RESET}")
                for f in res_aud.get("findings", []):
                    sev = f.get('severity', 'info').upper()
                    print(f"  • [{sev}] {P_BOLD}{f.get('title')}{RESET}: {f.get('description')}")
            else:
                print(f"{YELLOW}Comando não reconhecido: '{raw_cmd}'. Digite /help para ver os comandos.{RESET}")
    finally:
        await services.close()
        print(f"\n{P_MAIN}Sessão interativa do Achilles encerrada.{RESET}")
