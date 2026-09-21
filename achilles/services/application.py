"""Catálogo e contratos únicos para os transportes REST e MCP."""

import asyncio
import logging
from typing import Any, Dict, Literal, Optional, Type

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .action_resolver import ActionResolver
from .challenge_engine import ChallengeEngine
from .domain_memory import DomainMemoryEngine
from .errors import ServiceError
from .observation_engine import ObservationEngine
from .security_engine import SecurityAuditEngine
from .session_manager import BrowserSessionManager
from .traffic_journal import TrafficJournal
from .visual_report import export_report_to_file, generate_html_report


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PageArguments(Arguments):
    page_id: Optional[str] = Field(None, min_length=1, max_length=128)


class SelectArguments(Arguments):
    page_id: str = Field(min_length=1, max_length=128)


class NavigateArguments(PageArguments):
    url: str = Field(min_length=1, max_length=4096)
    wait_until: Literal["load", "domcontentloaded", "networkidle", "commit"] = "domcontentloaded"
    timeout_ms: int = Field(15000, ge=500, le=60000)


class NewTabArguments(Arguments):
    url: Optional[str] = Field(None, max_length=4096)


class CloseTabArguments(PageArguments):
    pass


class ScrollArguments(PageArguments):
    direction: Literal["up", "down", "top", "bottom"] = "down"
    amount: int = Field(500, ge=1, le=50000)
    selector: Optional[str] = Field(None, max_length=256)
    timeout_ms: int = Field(5000, ge=100, le=30000)


class SnapshotArguments(PageArguments):
    limit: int = Field(200, ge=1, le=1000)
    format: Literal["compact", "json", "markdown"] = "compact"
    in_viewport_only: bool = True
    selector: Optional[str] = Field(None, max_length=256)


class ReadArguments(PageArguments):
    max_length: int = Field(50000, ge=100, le=500000)


class ReportArguments(PageArguments):
    pass


class TrafficArguments(PageArguments):
    limit: int = Field(50, ge=1, le=500)


class CurlArguments(Arguments):
    request_id: str = Field(min_length=1, max_length=128)
    shell: Literal["posix", "powershell"] = "posix"


class ActionArguments(Arguments):
    action: Literal["click", "fill", "hover", "press", "select"]
    page_id: str = Field(min_length=1, max_length=128)
    snapshot_id: str = Field(min_length=1, max_length=128)
    element_ref: str = Field(min_length=1, max_length=256)
    value: Optional[str] = Field(None, max_length=65536)
    timeout_ms: int = Field(5000, ge=100, le=30000)

    @model_validator(mode="after")
    def value_required(self) -> "ActionArguments":
        if self.action in ("fill", "press", "select") and self.value is None:
            raise ValueError("A ação exige value")
        return self


class WaitForChallengeArguments(PageArguments):
    timeout_s: int = Field(120, ge=5, le=600)
    poll_interval_s: float = Field(1.5, ge=0.5, le=10.0)


class DomainMemoryArguments(Arguments):
    operation: Literal["get", "remember", "list", "clear"] = "get"
    domain: Optional[str] = Field(None, max_length=256)
    authenticated: Optional[bool] = None
    shortcuts: Optional[Dict[str, str]] = None
    api_endpoints: Optional[list] = None
    note: Optional[str] = Field(None, max_length=1000)


class ExportHtmlReportArguments(PageArguments):
    output_path: Optional[str] = Field(None, max_length=1024)


CONTRACTS: Dict[str, Type[Arguments]] = {
    "browser_status": Arguments,
    "browser_list_pages": Arguments,
    "browser_select_page": SelectArguments,
    "browser_new_tab": NewTabArguments,
    "browser_close_tab": CloseTabArguments,
    "browser_navigate": NavigateArguments,
    "browser_scroll": ScrollArguments,
    "browser_snapshot": SnapshotArguments,
    "browser_read_content": ReadArguments,
    "browser_report": ReportArguments,
    "browser_action": ActionArguments,
    "browser_wait_for_challenge": WaitForChallengeArguments,
    "browser_domain_memory": DomainMemoryArguments,
    "browser_export_html_report": ExportHtmlReportArguments,
    "network_query": TrafficArguments,
    "network_curl": CurlArguments,
    "network_postman": Arguments,
    "security_audit": PageArguments,
}
DESCRIPTIONS = {
    "browser_status": "Estado do transporte e da captura, sem conectar automaticamente.",
    "browser_list_pages": "Lista abas e frames disponíveis no Chrome conectado.",
    "browser_select_page": "Seleciona explicitamente uma aba e a traz para frente.",
    "browser_new_tab": "Abre uma nova aba no Chrome, opcionalmente navegando para uma URL.",
    "browser_close_tab": "Fecha a aba especificada ou a aba ativa atual.",
    "browser_navigate": "Navega a aba ativa ou especificada para uma URL com estratégia de espera.",
    "browser_scroll": "Rola a página ou container (up, down, top, bottom) para lazy-load ou infinite scroll.",
    "browser_snapshot": "Snapshot versionado, incluindo frames e Shadow DOM aberto.",
    "browser_read_content": "Lê o conteúdo principal da página em Markdown limpo (Reader Mode), eliminando scripts, estilos, anúncios e banners para máxima economia de tokens (~95%).",
    "browser_report": "Relatório executivo de economia de tokens e análise de rotas e tráfego de API da sessão.",
    "browser_action": "Executa Locator e retorna observação posterior; não repete a ação automaticamente.",
    "browser_wait_for_challenge": "Detecta desafios anti-bot (Turnstile, reCAPTCHA, hCaptcha, WAF) e 2FA/OTP, aguardando resolução humana cooperativa.",
    "browser_domain_memory": "Acessa e gerencia memória semântica persistente de autenticação, atalhos de rotas e APIs por domínio.",
    "browser_export_html_report": "Gera e exporta dashboard HTML standalone dark-mode com KPIs, métricas de tokens e rotas descobertas.",
    "network_query": "Últimos exchanges HTTP redigidos com status e response headers.",
    "network_curl": "Exporta um exchange redigido para POSIX ou PowerShell.",
    "network_postman": "Coleção Postman 2.1 com credenciais redigidas.",
    "security_audit": "Auditoria passiva com evidência e cobertura ausente explícitas.",
}


class ApplicationServices:
    def __init__(self, cdp_port: int = 9222) -> None:
        self.journal = TrafficJournal()
        self.session = BrowserSessionManager(cdp_port, self.journal)
        self.observations = ObservationEngine(self.session)
        self.actions = ActionResolver(self.session, self.observations)
        self.security = SecurityAuditEngine(self.session, self.journal)
        self.challenges = ChallengeEngine(self.session)
        self.domain_memory = DomainMemoryEngine()
        self.closed = False

    @staticmethod
    def tools() -> Dict[str, Any]:
        return {
            "tools": [
                {
                    "name": name,
                    "description": DESCRIPTIONS[name],
                    "inputSchema": contract.model_json_schema(),
                    "outputSchema": {"type": "object", "additionalProperties": True},
                    "annotations": {
                        "readOnlyHint": name not in ("browser_action", "browser_select_page", "browser_new_tab", "browser_close_tab", "browser_domain_memory"),
                        "destructiveHint": name in ("browser_action", "browser_close_tab"),
                        "idempotentHint": name not in ("browser_action", "browser_new_tab", "browser_close_tab"),
                        "openWorldHint": True,
                    },
                }
                for name, contract in CONTRACTS.items()
            ]
        }

    async def call(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return await asyncio.wait_for(self._invoke(name, arguments), timeout=90)
        except asyncio.TimeoutError as exc:
            raise ServiceError(
                "OPERATION_TIMEOUT", "Operação excedeu o prazo; observe o estado antes de repetir."
            ) from exc
        except ServiceError:
            raise
        except Exception as exc:
            logging.getLogger(__name__).error("Falha em %s: %s", name, type(exc).__name__)
            raise ServiceError(
                "INTERNAL_ERROR", "Falha interna; nenhum detalhe sensível foi retornado."
            ) from exc

    async def _invoke(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if name not in CONTRACTS:
            raise ServiceError("UNKNOWN_TOOL", "Ferramenta desconhecida.")
        if self.closed:
            raise ServiceError("SESSION_CLOSED", "Serviços encerrados.")
        try:
            args = CONTRACTS[name].model_validate(arguments).model_dump()
        except ValidationError as exc:
            raise ServiceError(
                "INVALID_ARGUMENT", "Argumentos não correspondem ao inputSchema."
            ) from exc
        if name == "browser_status":
            return {
                "cdp_url": self.session.cdp_url,
                "mode": "attach",
                "generation": self.session.generation,
                "recorded_requests": len(self.journal.records),
                "dropped_events": self.journal.dropped_events,
            }
        if name == "browser_list_pages":
            return await self.session.list_pages()
        if name == "browser_select_page":
            return await self.session.select_page(**args)
        if name == "browser_new_tab":
            return await self.session.new_page(**args)
        if name == "browser_close_tab":
            return await self.session.close_page(**args)
        if name == "browser_navigate":
            return await self.session.navigate(**args)
        if name == "browser_scroll":
            return await self.session.scroll(**args)
        if name == "browser_snapshot":
            return await self.observations.snapshot(**args)
        if name == "browser_read_content":
            return await self.observations.read_content(**args)
        if name == "browser_report":
            return await self.get_report(**args)
        if name == "browser_action":
            return await self.actions.execute(**args)
        if name == "browser_wait_for_challenge":
            return await self.challenges.wait_for_resolution(**args)
        if name == "browser_domain_memory":
            op = args.get("operation", "get")
            dom = args.get("domain")
            if op == "list":
                return {"domains": self.domain_memory.list_all()}
            if op == "clear":
                if dom:
                    return {"cleared": self.domain_memory.clear(dom), "domain": dom}
                return {"cleared": self.domain_memory.clear()}
            if not dom:
                _, page = await self.session.page(None)
                dom = page.url
            if op == "remember":
                return self.domain_memory.remember(
                    url_or_domain=dom,
                    authenticated=args.get("authenticated"),
                    shortcuts=args.get("shortcuts"),
                    api_endpoints=args.get("api_endpoints"),
                    note=args.get("note"),
                )
            return self.domain_memory.get(dom)
        if name == "browser_export_html_report":
            report_data = await self.get_report(args.get("page_id"))
            out_path = args.get("output_path")
            if out_path:
                filepath = export_report_to_file(report_data, out_path)
                return {"exported": True, "filepath": filepath, "report_path": filepath}
            html = generate_html_report(report_data)
            return {"exported": True, "html": html}
        if name == "network_query":
            await self.session.connect()
            await self.session.drain()
            return {
                "records": self.journal.query(**args),
                "dropped_events": self.journal.dropped_events,
            }
        if name == "network_postman":
            return self.journal.postman()
        if name == "network_curl":
            record = next(
                (r for r in self.journal.records if r["request_id"] == args["request_id"]), None
            )
            if record is None:
                raise ServiceError("RECORD_NOT_FOUND", "Exchange expirado ou inexistente.")
            return {
                "shell": args["shell"],
                "redacted": True,
                "curl": self.journal.to_curl(record, args["shell"]),
            }
        return await self.security.audit(**args)

    async def get_report(self, page_id: Optional[str] = None) -> Dict[str, Any]:
        token_metrics = self.observations.get_token_metrics()
        routes_report = self.journal.get_routes_report(page_id)
        try:
            _, page = await self.session.page(page_id)
            domain_mem = self.domain_memory.get(page.url)
        except Exception:
            domain_mem = None
        return {
            "token_metrics": token_metrics,
            "routes_report": routes_report,
            "domain_memory": domain_mem,
            "stealth": {
                "automation_controlled_disabled": True,
                "navigator_webdriver_masked": True,
                "persistent_profile_active": True,
                "secret_redaction_active": True,
                "canvas_2d_noise_active": True,
                "webgl_vendor_spoofing_active": True,
                "audio_buffer_jitter_active": True,
            },
        }

    async def close(self) -> None:
        await self.observations.close()
        await self.session.close()
        self.journal.clear()
        self.closed = True
