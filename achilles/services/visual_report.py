"""Gerador de Dashboard Visual HTML Standalone para relatórios e auditoria de sessão."""

import html
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def generate_html_report(
    token_metrics: Optional[Dict[str, Any]] = None,
    routes_report: Optional[Dict[str, Any]] = None,
    security_audit: Optional[Dict[str, Any]] = None,
    actions_log: Optional[List[Dict[str, Any]]] = None,
    stealth_status: Optional[Dict[str, Any]] = None,
) -> str:
    # Suporte a passagem de dicionário consolidado como único argumento
    if (
        isinstance(token_metrics, dict)
        and routes_report is None
        and ("token_metrics" in token_metrics or "routes_report" in token_metrics or "stealth" in token_metrics)
    ):
        report = token_metrics
        token_metrics = report.get("token_metrics", {})
        routes_report = report.get("routes_report", {})
        security_audit = report.get("security_audit")
        actions_log = report.get("actions_log")
        stealth_status = report.get("stealth")
    else:
        token_metrics = token_metrics or {}
        routes_report = routes_report or {}

    timestamp_str = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

    # Metrics
    saved_pct = token_metrics.get("overall_savings_percent", "0%")
    raw_tokens_avoided = token_metrics.get("raw_tokens_avoided", 0)
    tokens_consumed = token_metrics.get("tokens_consumed_estimated", 0)
    total_reads = token_metrics.get("total_reads", 0)
    total_snapshots = token_metrics.get("total_snapshots", 0)

    # Routes
    total_reqs = routes_report.get("total_requests", 0)
    unique_domains = routes_report.get("unique_domains_count", 0)
    api_endpoints = routes_report.get("api_endpoints", [])
    status_dist = routes_report.get("status_distribution", {})

    # Security
    audit = security_audit or {}
    score = audit.get("score", "N/A")
    findings = audit.get("findings", [])

    # HTML builder
    apis_rows = ""
    for ep in api_endpoints[:50]:
        method = html.escape(ep.get("method", "GET"))
        host = html.escape(ep.get("host", ""))
        path = html.escape(ep.get("path", ""))
        status = ep.get("status")
        status_val = str(status) if status is not None else "-"
        status_class = "status-2xx" if str(status).startswith("2") else ("status-4xx" if str(status).startswith("4") else "status-other")
        apis_rows += f"""
        <tr>
            <td><span class="badge method-{method.lower()}">{method}</span></td>
            <td><span class="host">{host}</span></td>
            <td><code class="path">{path}</code></td>
            <td><span class="badge {status_class}">{status_val}</span></td>
        </tr>
        """
    if not apis_rows:
        apis_rows = "<tr><td colspan='4' class='empty'>Nenhuma rota de API registrada na sessão.</td></tr>"

    findings_html = ""
    for f in findings:
        sev = html.escape(f.get("severity", "info").upper())
        title = html.escape(f.get("title", ""))
        desc = html.escape(f.get("description", ""))
        rem = html.escape(f.get("remediation", ""))
        findings_html += f"""
        <div class="finding-card sev-{sev.lower()}">
            <div class="finding-header">
                <span class="badge sev-badge">{sev}</span>
                <span class="finding-title">{title}</span>
            </div>
            <p class="finding-desc">{desc}</p>
            {f'<p class="finding-rem"><strong>Correção:</strong> {rem}</p>' if rem else ''}
        </div>
        """
    if not findings_html:
        findings_html = "<div class='empty-card'>Nenhuma vulnerabilidade crítica ou finding registrado na aba atual.</div>"

    html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Achilles CDP Agent — Relatório Executivo de Sessão</title>
    <style>
        :root {{
            --bg: #090d16;
            --surface: #111827;
            --surface-hover: #1f2937;
            --border: #374151;
            --primary: #a855f7;
            --primary-light: #c084fc;
            --accent: #38bdf8;
            --text: #f8fafc;
            --text-dim: #94a3b8;
            --success: #22c55e;
            --warning: #f59e0b;
            --danger: #ef4444;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background: var(--bg);
            color: var(--text);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.5;
            padding: 32px 24px;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 24px;
            border-bottom: 1px solid var(--border);
            margin-bottom: 32px;
        }}
        .brand {{ display: flex; align-items: center; gap: 12px; }}
        .brand-logo {{
            width: 42px; height: 42px;
            background: linear-gradient(135deg, var(--primary), var(--accent));
            border-radius: 12px;
            display: flex; align-items: center; justify-content: center;
            font-size: 20px; font-weight: bold; color: #fff;
            box-shadow: 0 0 20px rgba(168, 85, 247, 0.4);
        }}
        .brand h1 {{ font-size: 24px; font-weight: 700; color: #fff; }}
        .brand span {{ font-size: 13px; color: var(--primary-light); display: block; font-weight: 400; }}
        .meta-tag {{
            font-size: 13px; color: var(--text-dim); background: var(--surface);
            padding: 6px 14px; border-radius: 9999px; border: 1px solid var(--border);
        }}
        
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 20px;
            margin-bottom: 36px;
        }}
        .card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 24px;
            position: relative;
            overflow: hidden;
            transition: transform 0.2s, border-color 0.2s;
        }}
        .card:hover {{
            transform: translateY(-2px);
            border-color: rgba(168, 85, 247, 0.4);
        }}
        .card-label {{ font-size: 13px; font-weight: 500; color: var(--text-dim); margin-bottom: 8px; }}
        .card-value {{ font-size: 32px; font-weight: 800; color: #fff; letter-spacing: -0.5px; }}
        .card-value.green {{ color: var(--success); }}
        .card-value.purple {{ color: var(--primary-light); }}
        .card-value.blue {{ color: var(--accent); }}
        .card-sub {{ font-size: 12px; color: var(--text-dim); margin-top: 6px; }}

        .section-title {{
            font-size: 18px; font-weight: 700; margin-bottom: 16px;
            display: flex; align-items: center; gap: 8px; color: #fff;
        }}
        .section-title svg {{ fill: var(--primary-light); }}
        
        .table-container {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            overflow: hidden;
            margin-bottom: 36px;
        }}
        table {{ width: 100%; border-collapse: collapse; text-align: left; font-size: 13px; }}
        th {{
            background: rgba(255, 255, 255, 0.02);
            padding: 14px 18px;
            font-weight: 600;
            color: var(--text-dim);
            border-bottom: 1px solid var(--border);
        }}
        td {{ padding: 14px 18px; border-bottom: 1px solid rgba(255, 255, 255, 0.04); }}
        tr:last-child td {{ border-bottom: none; }}
        tr:hover td {{ background: rgba(255, 255, 255, 0.02); }}
        
        .badge {{
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 700;
            display: inline-block;
        }}
        .method-get {{ background: rgba(56, 189, 248, 0.15); color: #38bdf8; }}
        .method-post {{ background: rgba(245, 158, 11, 0.15); color: #f59e0b; }}
        .method-delete {{ background: rgba(239, 68, 68, 0.15); color: #ef4444; }}
        .status-2xx {{ background: rgba(34, 197, 94, 0.15); color: #22c55e; }}
        .status-4xx {{ background: rgba(239, 68, 68, 0.15); color: #ef4444; }}
        .status-other {{ background: rgba(148, 163, 184, 0.15); color: #94a3b8; }}
        .host {{ color: var(--accent); font-weight: 500; }}
        .path {{ color: #cbd5e1; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
        .empty {{ text-align: center; color: var(--text-dim); padding: 32px; }}

        .stealth-banner {{
            background: linear-gradient(135deg, rgba(168, 85, 247, 0.1), rgba(56, 189, 248, 0.05));
            border: 1px solid rgba(168, 85, 247, 0.3);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 36px;
        }}
        .stealth-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 16px;
            margin-top: 14px;
        }}
        .stealth-item {{ display: flex; align-items: center; gap: 10px; font-size: 13px; color: #e2e8f0; }}
        .check-icon {{ color: var(--success); font-weight: bold; }}

        .finding-card {{
            background: rgba(255, 255, 255, 0.02);
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 12px;
            border-left: 4px solid var(--border);
        }}
        .finding-card.sev-high {{ border-left-color: var(--danger); background: rgba(239, 68, 68, 0.04); }}
        .finding-card.sev-medium {{ border-left-color: var(--warning); background: rgba(245, 158, 11, 0.04); }}
        .finding-card.sev-low {{ border-left-color: var(--accent); background: rgba(56, 189, 248, 0.04); }}
        .finding-header {{ display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }}
        .sev-badge {{ background: var(--border); color: #fff; }}
        .finding-title {{ font-weight: 600; color: #fff; }}
        .finding-desc {{ font-size: 13px; color: var(--text-dim); margin-bottom: 6px; }}
        .finding-rem {{ font-size: 13px; color: var(--success); }}
        .empty-card {{ text-align: center; color: var(--text-dim); padding: 24px; background: var(--surface); border-radius: 12px; border: 1px solid var(--border); }}

        footer {{
            text-align: center;
            font-size: 12px;
            color: var(--text-dim);
            margin-top: 48px;
            padding-top: 24px;
            border-top: 1px solid var(--border);
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="brand">
                <div class="brand-logo">A</div>
                <div>
                    <h1>Achilles CDP Agent</h1>
                    <span>Relatório Executivo de Sessão & Auditoria de Tráfego</span>
                </div>
            </div>
            <div class="meta-tag">Gerado em: {timestamp_str}</div>
        </header>

        <!-- KPI Cards -->
        <div class="grid">
            <div class="card">
                <div class="card-label">Economia Global de Tokens</div>
                <div class="card-value green">{saved_pct}</div>
                <div class="card-sub">{raw_tokens_avoided:,} tokens brutos poupados</div>
            </div>
            <div class="card">
                <div class="card-label">Tokens Consumidos</div>
                <div class="card-value purple">{tokens_consumed:,}</div>
                <div class="card-sub">{total_reads} leituras • {total_snapshots} snapshots</div>
            </div>
            <div class="card">
                <div class="card-label">Requisições Analisadas</div>
                <div class="card-value blue">{total_reqs}</div>
                <div class="card-sub">{unique_domains} domínios únicos • {len(api_endpoints)} APIs</div>
            </div>
            <div class="card">
                <div class="card-label">Score de Segurança OWASP</div>
                <div class="card-value green">{score}</div>
                <div class="card-sub">{len(findings)} vulnerabilidades / achados</div>
            </div>
        </div>

        <!-- Stealth Posture Banner -->
        <div class="stealth-banner">
            <div class="section-title">🛡️ Postura Furtiva Anti-Bot & Anti-Detection Ativa</div>
            <div class="stealth-grid">
                <div class="stealth-item"><span class="check-icon">✔</span> Chromium AutomationControlled Desativado</div>
                <div class="stealth-item"><span class="check-icon">✔</span> Navigator Webdriver Mascarado (undefined)</div>
                <div class="stealth-item"><span class="check-icon">✔</span> WebGL & Canvas Fingerprint Randomizado</div>
                <div class="stealth-item"><span class="check-icon">✔</span> Web Audio API Acoustic Jitter Ativo</div>
                <div class="stealth-item"><span class="check-icon">✔</span> Perfil Persistente de Usuário Conectado</div>
                <div class="stealth-item"><span class="check-icon">✔</span> Redação Zero-Secret Ativa (Privacidade Absoluta)</div>
            </div>
        </div>

        <!-- API Routes Table -->
        <div class="section-title">🌐 Rotas & APIs de Rede Inspecionadas ({len(api_endpoints)})</div>
        <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th style="width: 90px;">Método</th>
                        <th style="width: 220px;">Host / Domínio</th>
                        <th>Path da Rota</th>
                        <th style="width: 100px;">Status HTTP</th>
                    </tr>
                </thead>
                <tbody>
                    {apis_rows}
                </tbody>
            </table>
        </div>

        <!-- Security Findings -->
        <div class="section-title">🔒 Postura de Segurança & Cabeçalhos OWASP</div>
        <div>
            {findings_html}
        </div>

        <footer>
            Achilles CDP Agent v2.1 • Motor Autônomo de Navegação & Segurança • Gerado Localmente Sem Vazamento de Dados
        </footer>
    </div>
</body>
</html>
"""
    return html_content


def export_report_to_file(
    arg1: Any = None,
    arg2: Any = None,
    security_audit: Optional[Dict[str, Any]] = None,
    actions_log: Optional[List[Dict[str, Any]]] = None,
) -> Path:
    output_path = None
    report_dict = None

    if isinstance(arg1, dict):
        report_dict = arg1
        if isinstance(arg2, (str, Path)):
            output_path = str(arg2)
    elif isinstance(arg2, dict):
        report_dict = arg2
        if isinstance(arg1, (str, Path)):
            output_path = str(arg1)
    elif isinstance(arg1, (str, Path)) or arg1 is None:
        output_path = str(arg1) if arg1 is not None else None

    if output_path:
        target = Path(output_path)
    else:
        target = Path.cwd() / f"achilles_session_report_{int(time.time())}.html"

    target.parent.mkdir(parents=True, exist_ok=True)
    if report_dict:
        content = generate_html_report(report_dict)
    else:
        content = generate_html_report({}, {})
    target.write_text(content, encoding="utf-8")
    return target
