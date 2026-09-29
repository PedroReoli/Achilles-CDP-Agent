"""
tui.py — Interface de Terminal Visual com Rich para o Achilles CDP Agent.
"""
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()


def render_banner():
    banner_text = """
   ___         __     _  __ __               _____   ___     ___                    __ 
  / _ | ____  / /    (_)/ // / ___  ___     / ___/  / _ \   / _ \  ___ _ ___  ___  / /_
 / __ |/ __/ / _ \  / // // / / -_)(_-<    / /__   / // /  / ___/ / _ `// -_)/ _ \/ __/
/_/ |_|\__/ /_//_/ /_//_//_/  \__//___/    \___/  /____/  /_/     \_, / \__/ /_//_/\__/ 
                                                                 /___/                  
    """
    console.print(Panel(Text(banner_text, style="bold cyan"), title="[bold white]Achilles CDP Agent[/bold white]", subtitle="[bold green]Achilles v2.1 — AI & DevTools Protocol Engine[/bold green]", border_style="cyan"))


def render_status_table(cdp_port: int, api_port: int, status: str, active_url: str, requests_count: int, risk_score: int):
    table = Table(title="[bold yellow]Status do Sistema & Bridge[/bold yellow]", border_style="blue")
    table.add_column("Módulo", style="cyan", justify="left")
    table.add_column("Porta / Endpoint", style="magenta", justify="center")
    table.add_column("Status", style="green", justify="center")
    table.add_column("Métrica / Detalhe", style="white", justify="left")

    table.add_row("Chrome CDP Target", f"127.0.0.1:{cdp_port}", f"[green]{status}[/green]", f"Aba: {active_url[:40]}")
    table.add_row("AI Bridge API", f"http://127.0.0.1:{api_port}", "[green]ONLINE[/green]", "Docs em /docs")
    table.add_row("Swagger Reverso", f"http://127.0.0.1:{api_port}/api/routes/swagger", "[green]ATIVO[/green]", f"{requests_count} APIs interceptadas")
    
    risk_color = "green" if risk_score < 20 else ("yellow" if risk_score < 50 else "red")
    table.add_row("OWASP Security Auditor", "/api/security/audit", f"[{risk_color}]SCORE: {risk_score}/100[/{risk_color}]", "Checagens passivas e ativas")

    console.print(table)
