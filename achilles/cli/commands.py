"""Comandos CLI e REPL Interativo do Achilles CDP Agent."""

import asyncio
import json
import sys
from typing import Any, Dict, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _print_banner():
    print("""
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
      Achilles CDP Agent — Autonomous Browser Automation & Security
""")


async def run_status(cdp_port: int) -> None:
    from achilles.services.application import ApplicationServices
    services = ApplicationServices(cdp_port)
    try:
        status = await services.call("browser_status", {})
        print("\n--- [ACHILLES CDP STATUS] ---")
        print(f"CDP URL:          {status.get('cdp_url')}")
        print(f"Modo:             {status.get('mode')}")
        print(f"Geração:          {status.get('generation')}")
        print(f"Reqs Gravadas:    {status.get('recorded_requests')}")
        print(f"Eventos Dropados: {status.get('dropped_events')}")
    finally:
        await services.close()


async def run_pages(cdp_port: int) -> None:
    from achilles.services.application import ApplicationServices
    services = ApplicationServices(cdp_port)
    try:
        res = await services.call("browser_list_pages", {})
        pages = res.get("pages", [])
        active_id = res.get("active_page_id")
        print(f"\n--- [PÁGINAS / ABAS DISPONÍVEIS ({len(pages)})] ---")
        if not pages:
            print("Nenhuma aba detectada. Certifique-se de que o Chrome está rodando com --remote-debugging-port.")
            return
        for idx, p in enumerate(pages, start=1):
            is_active = " [ATIVA]" if p.get("page_id") == active_id else ""
            print(f"[{idx}] ID: {p['page_id']}{is_active}")
            print(f"    Título: {p.get('title', '(Sem título)')}")
            print(f"    URL:    {p.get('url', 'about:blank')}")
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
        print(f"\n--- [SNAPSHOT SEMÂNTICO (ID: {res.get('snapshot_id')})] ---")
        print(f"Página: {res.get('page_id')} | Total Elementos: {len(res.get('elements', []))}")
        print("\n[Elementos Interativos]:")
        for line in res.get("compact", "").split("\n"):
            if line.strip():
                print(f"  {line}")
    finally:
        await services.close()


async def run_act(cdp_port: int, action: str, element_ref: str, value: Optional[str] = None, page_id: Optional[str] = None) -> None:
    from achilles.services.application import ApplicationServices
    services = ApplicationServices(cdp_port)
    try:
        # Obter snapshot mais recente para pegar o snapshot_id
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

        print(f"\n[*] Executando '{action}' em [{element_ref}] na página {snap['page_id']}...")
        res = await services.call("browser_action", args_act)
        print(f"[+] Status: {res.get('status')} | Duração: {res.get('duration_ms', 0)}ms")
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
        print(f"\n--- [HISTÓRICO DE TRÁFEGO ({len(records)} itens)] ---")
        for r in records:
            status = r.get("status") or "PEND"
            dur = f"{r.get('duration_ms', 0)}ms"
            print(f"[{r.get('request_id')}] [{r.get('method')}] {r.get('url')} (Status: {status}, {dur})")
    finally:
        await services.close()


async def run_curl(cdp_port: int, request_id: str, shell: str = "posix") -> None:
    from achilles.services.application import ApplicationServices
    services = ApplicationServices(cdp_port)
    try:
        res = await services.call("network_curl", {"request_id": request_id, "shell": shell})
        print(f"\n--- [CURL EXPORT ({shell.upper()})] ---")
        print(res.get("curl"))
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
        print(f"\n--- [AUDITORIA DE SEGURANÇA OWASP (Score: {score_str})] ---")
        print(f"URL: {res.get('url')}")
        findings = res.get("findings", [])
        print(f"Total de Achados: {len(findings)}\n")
        for f in findings:
            print(f"  • [{f.get('severity', 'info').upper()}] {f.get('title')}")
            if f.get('description'):
                print(f"    Descrição: {f.get('description')}")
            if f.get('remediation'):
                print(f"    Correção:  {f.get('remediation')}")
    finally:
        await services.close()


def ensure_chrome_running(cdp_port: int):
    import os
    import socket
    import subprocess
    import time
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
        print(f"[*] Chrome CDP não detectado na porta {cdp_port}.")
        print(f"[*] Iniciando Google Chrome com depuração na porta {cdp_port}...")
        proc = subprocess.Popen([chrome_bin, f"--remote-debugging-port={cdp_port}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2.0)
        return proc
    return None


async def run_interactive(cdp_port: int) -> None:
    from achilles.services.application import ApplicationServices
    _print_banner()
    spawned_proc = ensure_chrome_running(cdp_port)
    print(f"Conectando ao Chrome CDP na porta {cdp_port}...")
    services = ApplicationServices(cdp_port)
    current_page_id: Optional[str] = None
    latest_snapshot: Optional[Dict[str, Any]] = None

    print("\n[✓] Modo Interativo do Achilles iniciado!")
    print("    Digite 'help' para ver os comandos ou 'exit' para sair.\n")
    try:
        while True:
            try:
                prompt_label = f"achilles ({current_page_id or 'sem aba'})> "
                raw = await asyncio.to_thread(input, prompt_label)
            except (EOFError, KeyboardInterrupt):
                break
            
            line = raw.strip()
            if not line:
                continue
            
            parts = line.split()
            cmd = parts[0].lower()
            args = parts[1:]

            if cmd in ("exit", "quit", "q"):
                break
            elif cmd == "help":
                print("""
Comandos Disponíveis:
  status                     Mostra o status da conexão CDP e estatísticas
  pages                      Lista todas as abas abertas no navegador
  select <page_id>           Seleciona e foca uma aba específica
  goto <url>                 Navega a aba atual para uma URL
  snapshot                   Captura a árvore de elementos interativos
  click <ref>                Clica em um elemento pelo [ref] do snapshot
  fill <ref> <texto>         Digita texto em um campo pelo [ref]
  traffic [limit]            Lista o histórico de requisições de rede
  curl <req_id>              Gera o comando cURL seguro da requisição
  audit                      Executa auditoria de postura de segurança OWASP
  clear                      Limpa a tela do terminal
  exit                       Encerra o modo interativo
""")
            elif cmd == "clear":
                import os
                os.system("cls" if os.name == "nt" else "clear")
            elif cmd == "status":
                status = await services.call("browser_status", {})
                print(f"[STATUS] CDP: {status.get('cdp_url')} | Generation: {status.get('generation')} | Reqs: {status.get('recorded_requests')}")
            elif cmd == "pages":
                res = await services.call("browser_list_pages", {})
                pages = res.get("pages", [])
                print(f"Abas abertas ({len(pages)}):")
                for p in pages:
                    mark = " *" if p["page_id"] == current_page_id else ""
                    print(f"  [{p['page_id']}]{mark} {p.get('title', '')} -> {p.get('url')}")
                if pages and not current_page_id:
                    current_page_id = pages[0]["page_id"]
                    print(f"[*] Aba ativa definida para: {current_page_id}")
            elif cmd == "select":
                if not args:
                    print("Uso: select <page_id>")
                    continue
                target_id = args[0]
                await services.call("browser_select_page", {"page_id": target_id})
                current_page_id = target_id
                print(f"[+] Aba {target_id} selecionada!")
            elif cmd == "goto":
                if not args:
                    print("Uso: goto <url>")
                    continue
                url = args[0]
                if not url.startswith("http://") and not url.startswith("https://"):
                    url = "https://" + url
                if not current_page_id:
                    res_p = await services.call("browser_list_pages", {})
                    pages = res_p.get("pages", [])
                    if pages:
                        current_page_id = pages[0]["page_id"]
                    else:
                        print("[-] Nenhuma aba aberta para navegar.")
                        continue
                page_id_resolved, page_obj = await services.session.page(current_page_id)
                print(f"[*] Navegando para {url}...")
                await page_obj.goto(url, wait_until="domcontentloaded")
                print(f"[+] Navegação concluída!")
            elif cmd in ("snapshot", "snap"):
                res_snap = await services.call("browser_snapshot", {"page_id": current_page_id, "limit": 200})
                latest_snapshot = res_snap
                current_page_id = res_snap["page_id"]
                print(f"[+] Snapshot ID: {res_snap['snapshot_id']} (Total: {len(res_snap.get('elements', []))} elementos)")
                for line in res_snap.get("compact", "").split("\n"):
                    if line.strip():
                        print(f"  {line}")
            elif cmd == "click":
                if not args:
                    print("Uso: click <element_ref>")
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
                print(f"[+] Clique em [{ref}]: {res_act.get('status')}")
            elif cmd == "fill":
                if len(args) < 2:
                    print("Uso: fill <element_ref> <texto a preencher>")
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
                print(f"[+] Preenchimento de [{ref}] com '{text}': {res_act.get('status')}")
            elif cmd == "traffic":
                limit = int(args[0]) if args and args[0].isdigit() else 20
                res_tr = await services.call("network_query", {"page_id": current_page_id, "limit": limit})
                records = res_tr.get("records", [])
                print(f"Tráfego ({len(records)} requisições):")
                for r in records:
                    print(f"  [{r['request_id']}] [{r['method']}] {r['url']} (Status: {r.get('status')})")
            elif cmd == "curl":
                if not args:
                    print("Uso: curl <request_id>")
                    continue
                req_id = args[0]
                res_c = await services.call("network_curl", {"request_id": req_id, "shell": "powershell"})
                print(f"cURL:\n{res_c.get('curl')}")
            elif cmd == "audit":
                res_aud = await services.call("security_audit", {"page_id": current_page_id})
                score = res_aud.get("security_score")
                print(f"\n[AUDITORIA] Score: {score}/100 | URL: {res_aud.get('url')}")
                for f in res_aud.get("findings", []):
                    print(f"  • [{f.get('severity', 'info').upper()}] {f.get('title')}: {f.get('description')}")
            else:
                print(f"Comando não reconhecido: '{cmd}'. Digite 'help' para ver os comandos.")
    finally:
        await services.close()
        print("\nSessão interativa encerrada.")
