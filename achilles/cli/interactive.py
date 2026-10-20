"""Console interativo e protocolo de operação do Achilles."""

import asyncio
import os
from typing import Optional

from rich import box
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from achilles import __version__
from achilles.cli.commands import (
    ASCII_BANNER,
    console,
    ensure_chrome_running,
    get_chrome_profile_dir,
    run_audit,
    run_domain_memory,
    run_export_report,
    run_pages,
    run_read,
    run_report,
    run_snapshot,
    run_traffic,
    run_wait_challenge,
)
from achilles.cli.i18n import I18n


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



def run_protocol(lang: Optional[str] = None) -> None:
    from achilles.cli.i18n import get_stored_language
    is_pt = lang == "pt" or (lang is None and get_stored_language() == "pt")
    if is_pt:
        protocol_md = f"""# PROTOCOLO AGENTE AUTÔNOMO ACHILLES (v{__version__})

Você está conectado ao Achilles CDP Agent — uma ponte de automação e colaboração humano-IA no Chrome.

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

### 🛡️ PERFIL NATIVO & CADÊNCIA RESPONSÁVEL
- O Chrome usa perfil persistente e preserva os valores nativos de hardware, Canvas, WebGL e áudio para manter um ambiente coerente.
- CAPTCHA, 2FA e outros desafios devem ser resolvidos pela pessoa na janela do navegador; o Achilles detecta e aguarda, sem tentar contorná-los.
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
        protocol_md = f"""# ACHILLES CDP AGENT — AUTONOMOUS AGENT PROTOCOL (v{__version__})

You are operating the Achilles CDP Agent, a browser automation bridge designed for AI agents cooperating with human users.

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

### 🛡️ NATIVE PROFILE & RESPONSIBLE CADENCE
- Chrome uses a dedicated profile, keeps native hardware/Canvas/WebGL/audio values, masks basic automation signals, and exposes an optional closed Shadow DOM HUD.
- CAPTCHA, 2FA, and other challenges must be completed by the person in the browser; Achilles detects and waits without attempting a bypass.
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
                    console.print("[yellow]Uso/Usage: /select <# ou page_id>[/]")
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
                    await services.call("browser_scroll", {
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
                    console.print("[yellow]Uso/Usage: /click <element_ref>[/]")
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
                    console.print("[yellow]Uso/Usage: /fill <element_ref> <text>[/]")
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
                    console.print("[yellow]Uso/Usage: /curl <request_id>[/]")
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
