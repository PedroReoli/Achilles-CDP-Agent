"""Catálogo e contratos únicos para os transportes REST e MCP."""

import asyncio
import logging
import re
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Type

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .action_resolver import ActionResolver
from .agent_actions import AgentActions
from .bookmarks import BookmarkService
from .challenge_engine import ChallengeEngine
from .domain_memory import DomainMemoryEngine
from .errors import ServiceError
from .observation_engine import ObservationEngine
from .policy import PolicyEngine
from .redaction import redact, redact_url
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
    fast: bool = True


class ReadArguments(PageArguments):
    max_length: int = Field(50000, ge=100, le=500000)


class FindArguments(PageArguments):
    query: str = Field(min_length=1, max_length=512)
    limit: int = Field(20, ge=1, le=100)
    role: Optional[str] = Field(None, min_length=1, max_length=64)


class ExtractField(Arguments):
    selector: str = Field("", max_length=512)
    attribute: Optional[str] = Field(None, min_length=1, max_length=128)


class ExtractArguments(PageArguments):
    items_selector: str = Field(min_length=1, max_length=512)
    fields: Dict[str, ExtractField] = Field(min_length=1, max_length=50)
    limit: int = Field(100, ge=1, le=1000)

class FindAndActArguments(PageArguments):
    query: str = Field(min_length=1, max_length=512)
    action: Literal["click", "fill", "hover", "press", "select"]
    value: Optional[str] = Field(None, max_length=65536)
    role: Optional[str] = Field(None, min_length=1, max_length=64)
    timeout_ms: int = Field(5000, ge=100, le=30000)

class FillFormArguments(PageArguments):
    fields: Dict[str, str] = Field(min_length=1, max_length=100)
    submit_query: Optional[str] = Field(None, max_length=512)

class WaitStateArguments(PageArguments):
    text: Optional[str] = Field(None, max_length=512)
    url_contains: Optional[str] = Field(None, max_length=2048)
    timeout_ms: int = Field(15000, ge=100, le=60000)

class ScreenshotArguments(PageArguments):
    full_page: bool = False
    image_format: Literal["png", "jpeg"] = "png"

class UploadArguments(PageArguments):
    file_path: str = Field(min_length=1, max_length=2048)
    query: str = Field(min_length=1, max_length=512)

class DownloadArguments(PageArguments):
    query: str = Field(min_length=1, max_length=512)
    timeout_ms: int = Field(30000, ge=500, le=120000)

class DialogArguments(PageArguments):
    action: Literal["accept", "dismiss"]
    prompt_text: Optional[str] = Field(None, max_length=4096)
    timeout_ms: int = Field(15000, ge=100, le=60000)

class EventsArguments(Arguments):
    after: Optional[str] = Field(None, max_length=64)
    limit: int = Field(50, ge=1, le=200)

class PaginatedExtractArguments(ExtractArguments):
    next_query: Optional[str] = Field(None, max_length=512)
    max_pages: int = Field(10, ge=1, le=100)
    max_items: int = Field(1000, ge=1, le=10000)
    dedupe_by: Optional[List[str]] = Field(None, max_length=20)
    scroll: bool = False

class RecordingArguments(Arguments):
    operation: Literal["start", "stop", "status"]
    output_path: Optional[str] = Field(None, max_length=2048)

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
    verify: Literal["target", "snapshot", "none"] = "target"

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
    api_endpoints: Optional[List[str]] = None
    note: Optional[str] = Field(None, max_length=1000)


class ExportHtmlReportArguments(PageArguments):
    output_path: Optional[str] = Field(None, max_length=1024)


class BookmarkListArguments(Arguments):
    parent_id: Optional[str] = Field(None, min_length=1, max_length=128)
    limit: int = Field(100, ge=1, le=500)

class BookmarkSearchArguments(Arguments):
    query: str = Field(min_length=1, max_length=512)
    limit: int = Field(100, ge=1, le=500)


class BookmarkCreateArguments(Arguments):
    title: str = Field(min_length=1, max_length=512)
    url: str = Field(min_length=1, max_length=4096)
    parent_id: Optional[str] = Field(None, min_length=1, max_length=128)


class BookmarkUpdateArguments(Arguments):
    id: str = Field(min_length=1, max_length=128)
    title: Optional[str] = Field(None, min_length=1, max_length=512)
    url: Optional[str] = Field(None, min_length=1, max_length=4096)

    @model_validator(mode="after")
    def change_required(self) -> "BookmarkUpdateArguments":
        if self.title is None and self.url is None:
            raise ValueError("Informe title ou url")
        return self


class BookmarkRemoveArguments(Arguments):
    id: str = Field(min_length=1, max_length=128)


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
    "browser_find": FindArguments,
    "browser_extract": ExtractArguments,
    "browser_find_and_act": FindAndActArguments,
    "browser_fill_form": FillFormArguments,
    "browser_wait_for_state": WaitStateArguments,
    "browser_screenshot": ScreenshotArguments,
    "browser_upload": UploadArguments,
    "browser_download": DownloadArguments,
    "browser_handle_dialog": DialogArguments,
    "browser_events": EventsArguments,
    "browser_extract_paginated": PaginatedExtractArguments,
    "browser_recording": RecordingArguments,
    "browser_report": ReportArguments,
    "browser_action": ActionArguments,
    "browser_wait_for_challenge": WaitForChallengeArguments,
    "browser_domain_memory": DomainMemoryArguments,
    "browser_export_html_report": ExportHtmlReportArguments,
    "browser_bookmarks_list": BookmarkListArguments,
    "browser_bookmarks_search": BookmarkSearchArguments,
    "browser_bookmarks_create": BookmarkCreateArguments,
    "browser_bookmarks_update": BookmarkUpdateArguments,
    "browser_bookmarks_remove": BookmarkRemoveArguments,
    "network_query": TrafficArguments,
    "network_curl": CurlArguments,
    "network_postman": Arguments,
    "security_audit": PageArguments,
}
DESCRIPTIONS = {
    "browser_status": "Estado do transporte e da captura, sem conectar automaticamente.",
    "browser_list_pages": "Lista abas e frames disponíveis no navegador CDP conectado.",
    "browser_select_page": "Seleciona explicitamente uma aba e a traz para frente.",
    "browser_new_tab": "Abre uma nova aba no navegador, opcionalmente navegando para uma URL.",
    "browser_close_tab": "Fecha a aba especificada ou a aba ativa atual.",
    "browser_navigate": "Navega a aba ativa ou especificada para uma URL com estratégia de espera.",
    "browser_scroll": "Rola a página ou container (up, down, top, bottom) para lazy-load ou infinite scroll.",
    "browser_snapshot": "Snapshot versionado, incluindo frames e Shadow DOM aberto.",
    "browser_read_content": "Lê o conteúdo principal da página em Markdown limpo (Reader Mode), eliminando scripts, estilos, anúncios e banners para máxima economia de tokens (~95%).",
    "browser_find": "Busca elementos por texto, papel ou dica e retorna apenas correspondências com referências acionáveis.",
    "browser_extract": "Extrai registros estruturados por seletores CSS declarativos, sem executar JavaScript arbitrário.",
    "browser_find_and_act": "Localiza e executa uma ação, recuperando automaticamente referências inválidas uma vez.",
    "browser_fill_form": "Preenche vários campos por nome acessível e opcionalmente envia o formulário.",
    "browser_wait_for_state": "Aguarda texto ou mudança de URL sem polling pelo agente.",
    "browser_screenshot": "Salva screenshot em artefato local com hash e metadados.",
    "browser_upload": "Envia arquivo local para um input encontrado semanticamente, limitado a 50 MiB.",
    "browser_download": "Aciona e salva um download em diretório controlado pelo Achilles.",
    "browser_handle_dialog": "Aguarda e aceita ou dispensa alert, confirm ou prompt do navegador.",
    "browser_events": "Retorna eventos estruturados desde um cursor, para acompanhamento incremental.",
    "browser_extract_paginated": "Extrai múltiplas páginas ou infinite scroll com deduplicação e limites.",
    "browser_recording": "Grava operações de alto nível em workflow YAML sem valores de formulário.",
    "browser_report": "Relatório executivo de economia de tokens e análise de rotas e tráfego de API da sessão.",
    "browser_action": "Executa Locator e retorna observação posterior; não repete a ação automaticamente.",
    "browser_wait_for_challenge": "Detecta desafios anti-bot (Turnstile, reCAPTCHA, hCaptcha, WAF) e 2FA/OTP, aguardando resolução humana cooperativa.",
    "browser_domain_memory": "Acessa e gerencia memória semântica persistente de autenticação, atalhos de rotas e APIs por domínio.",
    "browser_export_html_report": "Gera e exporta dashboard HTML standalone dark-mode com KPIs, métricas de tokens e rotas descobertas.",
    "browser_bookmarks_list": "Lista pastas ou favoritos do perfil Chrome/Edge conectado.",
    "browser_bookmarks_search": "Busca favoritos por título ou URL no perfil Chrome/Edge conectado.",
    "browser_bookmarks_create": "Cria favorito HTTP(S) no navegador via extensão Achilles Browser Bridge.",
    "browser_bookmarks_update": "Edita título ou URL de favorito no navegador via extensão.",
    "browser_bookmarks_remove": "Remove um favorito ou uma pasta vazia pelo ID no navegador.",
    "network_query": "Últimos exchanges HTTP redigidos com status e response headers.",
    "network_curl": "Exporta um exchange redigido para POSIX ou PowerShell.",
    "network_postman": "Coleção Postman 2.1 com credenciais redigidas.",
    "security_audit": "Auditoria passiva com evidência e cobertura ausente explícitas.",
}

TOOLSETS = {
    "core": {
        "browser_status",
        "browser_list_pages",
        "browser_select_page",
        "browser_new_tab",
        "browser_close_tab",
        "browser_navigate",
        "browser_scroll",
        "browser_snapshot",
        "browser_read_content",
        "browser_find",
        "browser_extract",
        "browser_find_and_act",
        "browser_fill_form",
        "browser_wait_for_state",
        "browser_screenshot",
        "browser_upload",
        "browser_download",
        "browser_handle_dialog",
        "browser_events",
        "browser_extract_paginated",
        "browser_recording",
        "browser_action",
        "browser_wait_for_challenge",
    },
    "network": {"network_query", "network_curl", "network_postman"},
    "security": {"security_audit", "browser_report", "browser_export_html_report"},
    "memory": {"browser_domain_memory"},
    "bookmarks": {
        "browser_bookmarks_list",
        "browser_bookmarks_search",
        "browser_bookmarks_create",
        "browser_bookmarks_update",
        "browser_bookmarks_remove",
    },
}


def resolve_toolsets(value: str) -> Optional[set]:
    names = {item.strip().lower() for item in value.split(",") if item.strip()}
    if not names or "all" in names:
        return None
    unknown = names - set(TOOLSETS)
    if unknown:
        raise ValueError("Toolset desconhecido: " + ", ".join(sorted(unknown)))
    selected = set()
    for name in names:
        selected.update(TOOLSETS[name])
    return selected


class ApplicationServices:
    def __init__(self, cdp_port: int = 9222) -> None:
        self.journal = TrafficJournal()
        self.session = BrowserSessionManager(cdp_port, self.journal)
        self.observations = ObservationEngine(self.session)
        self.actions = ActionResolver(self.session, self.observations)
        self.agent_actions = AgentActions(self.session, self.observations, self.actions)
        self.bookmarks = BookmarkService(self.session)
        self.security = SecurityAuditEngine(self.session, self.journal)
        self.challenges = ChallengeEngine(self.session)
        self.domain_memory = DomainMemoryEngine()
        self.policy = PolicyEngine()
        self.closed = False
        self.events = deque(maxlen=200)
        self.challenge_events = deque(maxlen=50)
        self.recording = False
        self.recorded_steps: List[Dict[str, Any]] = []

    @staticmethod
    def tools(allowed_names: Optional[set] = None) -> Dict[str, Any]:
        output_schemas = {
            "browser_status": {
                "type": "object",
                "properties": {
                    "cdp_url": {"type": "string"},
                    "mode": {"type": "string"},
                    "generation": {"type": "integer"},
                    "recorded_requests": {"type": "integer"},
                    "dropped_events": {"type": "integer"},
                },
                "required": ["cdp_url", "mode", "generation", "recorded_requests"],
            },
            "browser_find": {
                "type": "object",
                "properties": {
                    "page_id": {"type": "string"},
                    "snapshot_id": {"type": "string"},
                    "query": {"type": "string"},
                    "matches": {"type": "array", "items": {"type": "object"}},
                    "match_count": {"type": "integer"},
                    "truncated": {"type": "boolean"},
                },
                "required": ["page_id", "snapshot_id", "query", "matches", "match_count"],
            },
            "browser_extract": {
                "type": "object",
                "properties": {
                    "page_id": {"type": "string"},
                    "url": {"type": "string"},
                    "items": {"type": "array", "items": {"type": "object"}},
                    "count": {"type": "integer"},
                    "truncated": {"type": "boolean"},
                },
                "required": ["page_id", "url", "items", "count", "truncated"],
            },
            "browser_action": {
                "type": "object",
                "properties": {
                    "status": {"type": "string"},
                    "action": {"type": "string"},
                    "page_id": {"type": "string"},
                    "url_after": {"type": "string"},
                    "duration_ms": {"type": "number"},
                    "verification": {"type": "object"},
                },
                "required": ["status", "action", "page_id", "duration_ms", "verification"],
            },
        }
        mutating = {
            "browser_select_page",
            "browser_new_tab",
            "browser_close_tab",
            "browser_navigate",
            "browser_scroll",
            "browser_action",
            "browser_find_and_act",
            "browser_fill_form",
            "browser_upload",
            "browser_download",
            "browser_handle_dialog",
            "browser_recording",
            "browser_domain_memory",
            "browser_export_html_report",
            "browser_bookmarks_create",
            "browser_bookmarks_update",
            "browser_bookmarks_remove",
        }
        destructive = {
            "browser_action",
            "browser_find_and_act",
            "browser_fill_form",
            "browser_close_tab",
            "browser_bookmarks_remove",
        }
        non_idempotent = {
            "browser_action",
            "browser_find_and_act",
            "browser_fill_form",
            "browser_download",
            "browser_handle_dialog",
            "browser_new_tab",
            "browser_close_tab",
            "browser_bookmarks_create",
            "browser_bookmarks_remove",
        }
        tools = []
        for name, contract in CONTRACTS.items():
            if allowed_names is not None and name not in allowed_names:
                continue
            tool = {
                "name": name,
                "description": DESCRIPTIONS[name],
                "inputSchema": contract.model_json_schema(),
                "annotations": {
                    "readOnlyHint": name not in mutating,
                    "destructiveHint": name in destructive,
                    "idempotentHint": name not in non_idempotent,
                    "openWorldHint": name.startswith(("browser_", "network_")),
                },
            }
            if name in output_schemas:
                tool["outputSchema"] = output_schemas[name]
            tools.append(tool)
        return {"tools": tools}

    async def call(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        started = time.perf_counter()
        operation_id = uuid.uuid4().hex
        outcome = "ok"
        try:
            current_url = ""
            if self.policy.config.get("domains") and not arguments.get("url") and name not in (
                "browser_status", "browser_list_pages", "browser_events",
                "browser_recording", "browser_domain_memory",
                "browser_bookmarks_list", "browser_bookmarks_search",
                "browser_bookmarks_create", "browser_bookmarks_update",
                "browser_bookmarks_remove",
            ):
                try:
                    _, current_page = await self.session.page(arguments.get("page_id"))
                    current_url = current_page.url
                except ServiceError:
                    pass
            self.policy.check(name, arguments, current_url)
            result = await asyncio.wait_for(self._invoke(name, arguments), timeout=90)
        except asyncio.TimeoutError as exc:
            outcome = "timeout"
            raise ServiceError(
                "OPERATION_TIMEOUT", "Operação excedeu o prazo; observe o estado antes de repetir."
            ) from exc
        except ServiceError as exc:
            outcome = "error"
            exc.operation_id = operation_id
            raise
        except Exception as exc:
            outcome = "error"
            logging.getLogger(__name__).error("Falha em %s: %s", name, type(exc).__name__)
            raise ServiceError(
                "INTERNAL_ERROR", "Falha interna; nenhum detalhe sensível foi retornado."
            ) from exc
        finally:
            if name not in ("browser_report", "browser_export_html_report", "browser_events"):
                self.events.append({
                    "operation_id": operation_id,
                    "at": time.time(),
                    "type": "operation.completed" if outcome == "ok" else "operation.failed",
                    "operation": name,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    "page_id": arguments.get("page_id"),
                    "status": outcome,
                })
        if name == "browser_navigate" and self.events:
            self.events[-1]["url"] = redact_url(result.get("url", ""))
        if name == "browser_snapshot":
            for warning in result.get("warnings", []):
                if warning.get("code") == "HUMAN_CHALLENGE_DETECTED":
                    self.challenge_events.append({"at": time.time(), "type": warning.get("type"), "status": "detected"})
        elif name == "browser_wait_for_challenge":
            self.challenge_events.append({"at": time.time(), "type": "human_assisted", "status": result.get("status")})
        if self.recording and outcome == "ok" and name != "browser_recording":
            self._record_step(name, arguments)
        return result

    def _record_step(self, name: str, arguments: Dict[str, Any]) -> None:
        operations = {
            "browser_navigate": "navigate",
            "browser_find_and_act": "find_and_act",
            "browser_fill_form": "fill_form",
            "browser_extract": "extract",
            "browser_extract_paginated": "extract_paginated",
            "browser_screenshot": "screenshot",
            "browser_upload": "upload",
            "browser_download": "download",
            "browser_wait_for_state": "wait_for",
            "browser_wait_for_challenge": "wait_challenge",
            "browser_handle_dialog": "dialog",
        }
        operation = operations.get(name)
        if not operation:
            return
        safe = redact(arguments)
        if operation == "fill_form":
            safe["fields"] = {
                key: "${" + (re.sub(r"[^A-Z0-9]+", "_", key.upper()).strip("_") or "INPUT") + "}"
                for key in arguments.get("fields", {})
            }
        if operation == "find_and_act" and arguments.get("action") == "fill":
            label = re.sub(r"[^A-Z0-9]+", "_", str(arguments.get("query", "VALUE")).upper()).strip("_")
            safe["value"] = "${" + (label or "VALUE") + "}"
        if operation == "upload" and safe.get("file_path"):
            safe["file_path"] = "${FILE_PATH}"
        self.recorded_steps.append({operation: safe})

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
        if name == "browser_find":
            return await self.observations.find(**args)
        if name == "browser_extract":
            return await self.observations.extract(**args)
        if name == "browser_find_and_act":
            return await self.agent_actions.find_and_act(**args)
        if name == "browser_fill_form":
            return await self.agent_actions.fill_form(**args)
        if name == "browser_wait_for_state":
            return await self.agent_actions.wait_for_state(**args)
        if name == "browser_screenshot":
            return await self.agent_actions.screenshot(**args)
        if name == "browser_upload":
            return await self.agent_actions.upload(**args)
        if name == "browser_download":
            return await self.agent_actions.download(**args)
        if name == "browser_handle_dialog":
            return await self.agent_actions.handle_dialog(**args)
        if name == "browser_events":
            events = list(self.events)
            if args.get("after"):
                index = next(
                    (i for i, event in enumerate(events) if event["operation_id"] == args["after"]),
                    -1,
                )
                events = events[index + 1 :] if index >= 0 else events
            events = events[-args["limit"] :]
            return {"events": events, "cursor": events[-1]["operation_id"] if events else args.get("after")}
        if name == "browser_extract_paginated":
            return await self.agent_actions.extract_paginated(**args)
        if name == "browser_recording":
            operation = args["operation"]
            if operation == "start":
                self.recording = True
                self.recorded_steps.clear()
                return {"status": "recording", "steps": 0}
            if operation == "status":
                return {
                    "status": "recording" if self.recording else "idle",
                    "steps": len(self.recorded_steps),
                }
            import yaml

            from .named_sessions import achilles_data_dir

            self.recording = False
            path = args.get("output_path") or str(
                achilles_data_dir() / "runs" / f"recording-{uuid.uuid4().hex}.yaml"
            )
            destination = Path(path).expanduser().resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            workflow = {"name": "recorded-workflow", "steps": self.recorded_steps}
            destination.write_text(
                yaml.safe_dump(workflow, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            return {
                "status": "stopped",
                "steps": len(self.recorded_steps),
                "path": str(destination),
            }
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
        if name.startswith("browser_bookmarks_"):
            return await self.bookmarks.call(name.removeprefix("browser_bookmarks_"), **args)
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
        request_history = [
            {
                "at": row["started_at"],
                "method": row["method"],
                "url": redact_url(row["url"]),
                "status": row["status"],
                "resource_type": row["resource_type"],
            }
            for row in self.journal.records
            if page_id is None or row.get("page_id") == page_id
        ][-100:]
        try:
            _, page = await self.session.page(page_id)
            domain_mem = self.domain_memory.get(page.url)
        except Exception:
            domain_mem = None
        return {
            "token_metrics": token_metrics,
            "routes_report": routes_report,
            "timeline": [event for event in self.events if page_id is None or event.get("page_id") in (None, page_id)],
            "request_history": request_history,
            "challenge_history": list(self.challenge_events),
            "domain_memory": domain_mem,
            "stealth": {
                "automation_controlled_disabled": True,
                "navigator_webdriver_masked": True,
                "persistent_profile_active": True,
                "secret_redaction_active": True,
                "native_fingerprint_preserved": True,
            },
        }

    async def close(self) -> None:
        await self.observations.close()
        await self.session.close()
        self.journal.clear()
        self.closed = True
