"""
e2e_workflow_demo.py — Demonstração de fluxo completo de ponta a ponta do Achilles CDP Agent.

Demonstra:
1. Verificação / inicialização segura do Google Chrome com perfil persistente.
2. Navegação para sites reais (Hacker News, GitHub).
3. Reader Mode com métricas de economia de tokens (~95%).
4. Captura de Snapshot Semântico com elementos interativos.
5. Exportação de Relatório Visual HTML standalone com dark-mode.
"""
import asyncio
import os
import sys
from pathlib import Path

# Garante saída UTF-8 no console do Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent))

from achilles.cli.commands import ensure_chrome_running
from achilles.cli.i18n import I18n
from achilles.services.application import ApplicationServices


async def main() -> None:
    print("=" * 60)
    print("🚀 ACHILLES CDP AGENT — E2E WORKFLOW DEMO")
    print("=" * 60)
    i18n = I18n(lang="pt")
    cdp_port = int(os.environ.get("ACHILLES_CDP_PORT", "9222"))

    # 1. Garante que o Chrome está rodando na porta CDP
    print(f"\n[1] Verificando / Inicializando Google Chrome na porta {cdp_port}...")
    ensure_chrome_running(cdp_port, i18n)

    svc = ApplicationServices(cdp_port=cdp_port)
    try:
        # 2. Navegação: Hacker News
        print("\n[2] Navegando para Hacker News (https://news.ycombinator.com)...")
        res_open = await svc.call("browser_navigate", {"url": "https://news.ycombinator.com"})
        print(f"    ✔ Título: {res_open.get('title')}")
        print(f"    ✔ URL:    {res_open.get('url')}")

        # 3. Reader Mode: Extração sem ruído e métricas de tokens
        print("\n[3] Executando Reader Mode no Hacker News...")
        res_read = await svc.call("browser_read_content", {"max_length": 600})
        saved = res_read.get("tokens_saved_percent", "N/A")
        print(f"    ✔ Economia de Tokens: {saved}")
        preview = (res_read.get("markdown") or "").strip()[:200]
        print(f"    ✔ Conteúdo extraído:\n      {preview}...")

        # 4. Snapshot Semântico
        print("\n[4] Capturando Snapshot Semântico do viewport...")
        res_snap = await svc.call("browser_snapshot", {"limit": 10, "in_viewport_only": True})
        elements = res_snap.get("elements", [])
        print(f"    ✔ Elementos interativos encontrados: {len(elements)}")
        for el in elements[:5]:
            print(f"      • [{el.get('element_ref')}] {el.get('role')}: {el.get('name', '')[:40]}")

        # 5. Navegação: Repositório GitHub
        print("\n[5] Navegando para o repositório GitHub do Achilles...")
        res_gh = await svc.call("browser_navigate", {"url": "https://github.com/PedroReoli/Achilles-CDP-Agent"})
        print(f"    ✔ Título: {res_gh.get('title')}")

        # 6. Reader Mode no GitHub
        print("\n[6] Extraindo README do GitHub via Reader Mode...")
        res_gh_read = await svc.call("browser_read_content", {"max_length": 800})
        print(f"    ✔ Economia de Tokens: {res_gh_read.get('tokens_saved_percent', 'N/A')}")

        # 7. Exportação de Relatório Visual HTML
        print("\n[7] Exportando Relatório Visual HTML...")
        report_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "achilles_demo_report.html"))
        res_rep = await svc.call("browser_export_html_report", {"output_path": report_file})
        print(f"    ✔ Relatório gerado com sucesso em:\n      {res_rep.get('report_path')}")

        print("\n" + "=" * 60)
        print("✔ FLUXO E2E CONCLUÍDO COM 100% DE SUCESSO!")
        print("=" * 60)

    except Exception as exc:
        print(f"\n❌ Erro durante o workflow: {exc}")
        import traceback
        traceback.print_exc()
    finally:
        await svc.close()


if __name__ == "__main__":
    asyncio.run(main())
