"""
app.py — CLI do Achilles CDP Agent com Typer e subcomandos.
"""
import asyncio
import typer
import uvicorn
from achilles.cli.tui import render_banner, render_status_table, console
from achilles.api.server import app as fastapi_app
from achilles.mcp.server import run_mcp_stdio

cli = typer.Typer(
    name="achilles",
    help="Achilles CDP Agent — Interface CLI para Automação, Engenharia Reversa e Auditoria via Chrome DevTools Protocol."
)


@cli.command("start")
def start_server(
    port: int = typer.Option(8765, "--port", "-p", help="Porta para o servidor FastAPI Bridge"),
    cdp_port: int = typer.Option(9222, "--cdp-port", "-c", help="Porta do Chrome CDP"),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host de ligação")
):
    """Inicia o servidor AI Bridge e a interface interativa no terminal."""
    render_banner()
    render_status_table(cdp_port=cdp_port, api_port=port, status="CONNECTING", active_url="http://localhost:9222", requests_count=0, risk_score=0)
    console.print(f"\n[bold green]✓ Achilles CDP Agent rodando em http://{host}:{port}[/bold green]")
    console.print("[dim]Pressione Ctrl+C para encerrar o servidor.[/dim]\n")
    uvicorn.run(fastapi_app, host=host, port=port, log_level="warning")


@cli.command("mcp")
def start_mcp():
    """Inicia o servidor MCP (Model Context Protocol) via stdio para Claude Desktop / Cursor."""
    asyncio.run(run_mcp_stdio())


def main():
    cli()
