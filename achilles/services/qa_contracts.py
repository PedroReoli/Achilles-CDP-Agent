"""Contratos públicos do runtime de QA para CLI, REST e MCP."""

from typing import Any, Dict, List, Literal, Optional, Type

from pydantic import BaseModel, ConfigDict, Field, model_validator


class QaArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class QaAssertion(QaArguments):
    kind: Literal[
        "status",
        "header_exists",
        "header_equals",
        "body_contains",
        "json_path_equals",
        "response_time_ms",
        "schema_required",
    ]
    key: Optional[str] = Field(None, max_length=512)
    expected: Any = None


class QaCase(QaArguments):
    id: Optional[str] = Field(None, max_length=128)
    name: str = Field(min_length=1, max_length=256)
    method: Literal["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"] = "GET"
    path: Optional[str] = Field(None, max_length=4096)
    url: Optional[str] = Field(None, max_length=4096)
    headers: Dict[str, str] = Field(default_factory=dict, max_length=50)
    query: Dict[str, str] = Field(default_factory=dict, max_length=100)
    json_body: Any = None
    timeout_ms: int = Field(10000, ge=100, le=120000)
    expected_status: List[int] = Field(default_factory=lambda: [200], min_length=1, max_length=20)
    assertions: List[QaAssertion] = Field(default_factory=list, max_length=50)
    allow_mutating: bool = False
    tags: List[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def target_required(self) -> "QaCase":
        if self.path is None and self.url is None:
            raise ValueError("Informe path ou url")
        if self.path is not None and self.url is not None:
            raise ValueError("Informe somente path ou url")
        return self


class QaSuite(QaArguments):
    name: str = Field(min_length=1, max_length=256)
    base_url: Optional[str] = Field(None, max_length=4096)
    variables: Dict[str, str] = Field(default_factory=dict, max_length=100)
    cases: List[QaCase] = Field(min_length=1, max_length=200)
    concurrency: int = Field(4, ge=1, le=10)
    stop_on_failure: bool = False


class QaDiscoverArguments(QaArguments):
    openapi: Optional[str] = Field(None, max_length=4096)
    base_url: Optional[str] = Field(None, max_length=4096)
    include_traffic: bool = True
    page_id: Optional[str] = Field(None, max_length=128)
    limit: int = Field(200, ge=1, le=500)


class QaPlanArguments(QaArguments):
    endpoints: List[Dict[str, Any]] = Field(min_length=1, max_length=500)
    suite_name: str = Field("generated-smoke", min_length=1, max_length=256)
    base_url: Optional[str] = Field(None, max_length=4096)
    include_mutating: bool = False


class QaRequestArguments(QaArguments):
    method: Literal["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"] = "GET"
    url: str = Field(min_length=1, max_length=4096)
    headers: Dict[str, str] = Field(default_factory=dict, max_length=50)
    query: Dict[str, str] = Field(default_factory=dict, max_length=100)
    json_body: Any = None
    timeout_ms: int = Field(10000, ge=100, le=120000)
    expected_status: List[int] = Field(default_factory=lambda: [200], min_length=1, max_length=20)
    assertions: List[QaAssertion] = Field(default_factory=list, max_length=50)
    allow_mutating: bool = False


class QaRunSuiteArguments(QaArguments):
    suite: Optional[QaSuite] = None
    path: Optional[str] = Field(None, max_length=2048)
    variables: Dict[str, str] = Field(default_factory=dict, max_length=100)

    @model_validator(mode="after")
    def exactly_one_source(self) -> "QaRunSuiteArguments":
        if (self.suite is None) == (self.path is None):
            raise ValueError("Informe exatamente um entre suite e path")
        return self


class QaReportArguments(QaArguments):
    run_id: Optional[str] = Field(None, max_length=128)
    format: Literal["json", "html", "junit"] = "json"
    output_path: Optional[str] = Field(None, max_length=2048)


class QaSecurityAuditArguments(QaArguments):
    urls: List[str] = Field(default_factory=list, max_length=50)
    include_traffic: bool = True
    page_id: Optional[str] = Field(None, max_length=128)
    timeout_ms: int = Field(10000, ge=100, le=60000)


class QaRunsArguments(QaArguments):
    limit: int = Field(20, ge=1, le=100)


QA_CONTRACTS: Dict[str, Type[BaseModel]] = {
    "qa_status": QaArguments,
    "qa_discover": QaDiscoverArguments,
    "qa_plan": QaPlanArguments,
    "qa_request": QaRequestArguments,
    "qa_run_suite": QaRunSuiteArguments,
    "qa_report": QaReportArguments,
    "qa_security_audit": QaSecurityAuditArguments,
    "qa_runs": QaRunsArguments,
}

QA_DESCRIPTIONS = {
    "qa_status": "Estado, políticas e capacidades do runtime local de QA.",
    "qa_discover": "Descobre endpoints pelo tráfego capturado e por OpenAPI JSON/YAML.",
    "qa_plan": "Converte endpoints descobertos em uma suíte revisável, sem executá-la.",
    "qa_request": "Executa um caso HTTP autorizado com assertions e evidência redigida.",
    "qa_run_suite": "Executa uma suíte QA declarativa com concorrência limitada e relatório persistente.",
    "qa_report": "Lê ou exporta uma execução QA em JSON, HTML ou JUnit XML.",
    "qa_security_audit": "Auditoria defensiva de headers, cookies, CORS e exposição de servidor.",
    "qa_runs": "Lista execuções QA persistidas mais recentes.",
}

QA_TOOLSET = set(QA_CONTRACTS)
QA_MUTATING = {"qa_request", "qa_run_suite"}
QA_DESTRUCTIVE = {"qa_request", "qa_run_suite"}
QA_NON_IDEMPOTENT = {"qa_request", "qa_run_suite"}
