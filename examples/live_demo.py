"""Live Demo do Achilles CDP Agent — Demonstração Prática de Funcionalidades.

Executa uma sessão de automação ponta a ponta com:
1. Conexão CDP e Registro de Targets
2. Extração de Snapshot Semântico (AXTree)
3. Resolução de Ação Segura via Locator
4. Gravação no TrafficJournal com Redação de Segredos
5. Auditoria de Segurança OWASP em Headers Reais de Resposta
"""

import asyncio
import json
import os
import socket
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from playwright.async_api import async_playwright
from achilles.services.application import ApplicationServices


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def run_demo():
    print("=" * 60)
    print("🚀 INICIANDO TESTE AO VIVO DO ACHILLES CDP AGENT")
    print("=" * 60)

    # 1. Verificar se Chrome real está aberto na 9222 ou subir um Chromium local com CDP
    cdp_port = 9222
    browser_server = None
    playwright_instance = None

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            s.connect(("127.0.0.1", 9222))
            print("\n[+] Detectado Chrome rodando na porta 9222!")
    except Exception:
        cdp_port = find_free_port()
        print(f"\n[*] Chrome 9222 não detectado. Subindo instância Chromium dedicada na porta CDP {cdp_port}...")
        playwright_instance = await async_playwright().start()
        browser_server = await playwright_instance.chromium.launch(
            args=[f"--remote-debugging-port={cdp_port}"],
            headless=True
        )
        context = await browser_server.new_context()
        await context.new_page()

    # 2. Inicializar Application Services
    services = ApplicationServices(cdp_port=cdp_port)
    
    try:
        # 3. Listar targets / páginas
        print("\n--- [ETAPA 1: SESSÃO & TARGETS (browser_list_pages)] ---")
        pages_res = await services.call("browser_list_pages", {})
        pages = pages_res.get("pages", [])
        print(f"[+] Total de páginas conectadas: {len(pages)}")
        for p in pages:
            print(f"    - ID: {p['page_id']} | Título: {p.get('title', '')} | URL: {p['url']}")

        # Selecionar a primeira página disponível ou usar a ativa
        selected_page = pages_res.get("active_page_id") or (pages[0]["page_id"] if pages else None)
        
        # Se temos uma página, vamos navegar ou usar a aba existente
        page_id, page_obj = await services.session.page(selected_page)
        print("\n--- [ETAPA 2: NAVEGAÇÃO & CARREGAMENTO DE FORMULÁRIO] ---")
        print("[*] Navegando para 'https://httpbin.org/forms/post'...")
        await page_obj.goto("https://httpbin.org/forms/post", wait_until="domcontentloaded")
        print(f"[+] Navegação concluída na página: {page_id}")

        # 4. Capturar Snapshot Semântico com ObservationEngine
        print("\n--- [ETAPA 3: OBSERVAÇÃO SEMÂNTICA (browser_snapshot / AXTree)] ---")
        snapshot = await services.call("browser_snapshot", {"page_id": selected_page, "limit": 200})
        snapshot_id = snapshot["snapshot_id"]
        elements = snapshot.get("elements", [])
        print(f"[+] Snapshot ID: {snapshot_id}")
        print(f"[+] Elementos interativos detectados: {len(elements)}")
        print("\n[Visualização Compacta para IA (Amostra)]:")
        for line in snapshot.get("compact", "").split("\n")[:8]:
            print(f"    {line}")

        # 5. Executar Ação com ActionResolver (Preencher campo e Clicar)
        print("\n--- [ETAPA 4: AÇÕES VIA ACTION RESOLVER COM AUTO-WAIT (browser_action)] ---")
        input_elem = next((e for e in elements if e["role"] == "textbox" or "custname" in e.get("name", "")), None)
        if input_elem:
            ref = input_elem["element_ref"]
            print(f"[*] Preenchendo campo [{ref}] ('{input_elem.get('name', '')}') com 'Pedro Lucas - Reoli'...")
            action_res = await services.call("browser_action", {
                "page_id": selected_page,
                "snapshot_id": snapshot_id,
                "element_ref": ref,
                "action": "fill",
                "value": "Pedro Lucas - Reoli",
                "timeout_ms": 5000
            })
            print(f"[+] Resultado do Preenchimento: {action_res.get('status', 'OK')}")

        # 6. Inspecionar TrafficJournal
        print("\n--- [ETAPA 5: TRAFFIC JOURNAL & REDAÇÃO DE DADOS (network_query)] ---")
        traffic = await services.call("network_query", {"page_id": selected_page, "limit": 10})
        records = traffic.get("records", [])
        print(f"[+] Requisições capturadas no Journal: {len(records)}")
        for req in records[:4]:
            print(f"    [{req['method']}] {req['url']} -> Status: {req.get('status')} ({req.get('duration_ms', 0)}ms)")

        # Se houver requisições, gerar comando cURL
        if records:
            req_id = records[0]["request_id"]
            curl_res = await services.call("network_curl", {"request_id": req_id, "shell": "powershell"})
            print("\n[Comando cURL gerado pelo Achilles (Redacted)]:")
            print(f"    {curl_res.get('curl')}")

        # 7. Auditoria de Segurança OWASP em Headers Reais
        print("\n--- [ETAPA 6: AUDITORIA DE SEGURANÇA OWASP (security_audit)] ---")
        audit = await services.call("security_audit", {"page_id": selected_page})
        print(f"[+] Score de Segurança: {audit.get('security_score', 'N/A')}/100")
        findings = audit.get("findings", [])
        print(f"[+] Total de Achados de Postura: {len(findings)}")
        for f in findings[:4]:
            print(f"    - [{f.get('severity', 'info').upper()}] {f.get('title')}: {f.get('description')}")

        print("\n" + "=" * 60)
        print("✅ TESTE CONCLUÍDO COM SUCESSO! TODAS AS CAMADAS OPERACIONAIS.")
        print("=" * 60)

    finally:
        await services.close()
        if browser_server:
            await browser_server.close()
        if playwright_instance:
            await playwright_instance.stop()


if __name__ == "__main__":
    asyncio.run(run_demo())
