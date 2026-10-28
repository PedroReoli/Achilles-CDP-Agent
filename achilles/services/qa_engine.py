"""Motor HTTP de QA com escopo explícito, assertions e evidências persistentes."""

import asyncio
import html
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
import yaml

from .errors import ServiceError
from .named_sessions import achilles_data_dir
from .policy import PolicyEngine
from .qa_contracts import QaAssertion, QaCase, QaSuite
from .redaction import redact, redact_body, redact_url

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
HTTP_METHODS = SAFE_METHODS | {"POST", "PUT", "PATCH", "DELETE"}
OPENAPI_METHODS = {method.lower() for method in HTTP_METHODS}


def _replace_variables(value: Any, variables: Dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {key: _replace_variables(item, variables) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_variables(item, variables) for item in value]
    if not isinstance(value, str):
        return value

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        resolved = variables.get(key, os.environ.get(f"ACHILLES_QA_VAR_{key}"))
        if resolved is None:
            raise ServiceError("QA_INPUT_REQUIRED", f"Defina ACHILLES_QA_VAR_{key}.")
        return str(resolved)

    return re.sub(r"\$\{([A-Z][A-Z0-9_]*)\}", replace, value)


def _json_path(payload: Any, path: str) -> Any:
    current = payload
    for part in path.strip("$.").split(".") if path.strip("$.") else []:
        if isinstance(current, list) and part.isdigit():
            current = current[int(part)]
        elif isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise KeyError(path)
    return current


def _redact_html_tokens(body: str) -> str:
    """Remove tokens efêmeros comuns em metatags antes de persistir evidência."""
    pattern = re.compile(
        r"(<meta\s+[^>]*name=[\"'](?:achilles-token|csrf-token|xsrf-token)[\"']"
        r"[^>]*content=[\"'])[^\"']+([\"'][^>]*>)",
        re.IGNORECASE,
    )
    return pattern.sub(r"\1[REDACTED]\2", body)


class QaEngine:
    def __init__(self, policy: PolicyEngine) -> None:
        self.policy = policy
        self.root = achilles_data_dir() / "qa"
        self.runs_root = self.root / "runs"
        self.runs_root.mkdir(parents=True, exist_ok=True)
        self.client = httpx.AsyncClient(
            follow_redirects=False,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            headers={"User-Agent": "Achilles-QA/2"},
        )

    async def close(self) -> None:
        await self.client.aclose()

    @staticmethod
    def endpoint_from_url(method: str, url: str, **extra: Any) -> Dict[str, Any]:
        split = urlsplit(url)
        clean = urlunsplit((split.scheme, split.netloc, split.path or "/", "", ""))
        return {"method": method.upper(), "url": clean, "path": split.path or "/", **extra}

    def discover_traffic(
        self, records: Iterable[Dict[str, Any]], page_id: Optional[str], limit: int
    ) -> List[Dict[str, Any]]:
        endpoints: Dict[tuple[str, str], Dict[str, Any]] = {}
        for row in list(records)[-limit:]:
            if page_id is not None and row.get("page_id") != page_id:
                continue
            method = str(row.get("method", "GET")).upper()
            url = str(row.get("url", ""))
            if not url.startswith(("http://", "https://")):
                continue
            endpoint = self.endpoint_from_url(
                method,
                url,
                source="traffic",
                observed_status=row.get("status"),
                expected_status=[row["status"]] if isinstance(row.get("status"), int) else None,
                content_type=str(row.get("response_headers", {}).get("content-type", "")),
            )
            endpoints[(method, endpoint["url"])] = endpoint
        return sorted(endpoints.values(), key=lambda item: (item["url"], item["method"]))

    async def load_openapi(self, source: str) -> Dict[str, Any]:
        if source.startswith(("http://", "https://")):
            self.policy.check_qa(source, "GET")
            try:
                response = await self.client.get(source, timeout=15.0)
                response.raise_for_status()
                if len(response.content) > 2 * 1024 * 1024:
                    raise ServiceError("QA_SPEC_TOO_LARGE", "OpenAPI limitado a 2 MiB.")
                raw = response.text
            except httpx.HTTPError as exc:
                raise ServiceError("QA_HTTP_ERROR", "Não foi possível carregar o OpenAPI.") from exc
        else:
            path = Path(source).expanduser().resolve()
            if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
                raise ServiceError("QA_SPEC_NOT_FOUND", "OpenAPI inexistente ou maior que 2 MiB.")
            raw = path.read_text(encoding="utf-8")
        try:
            payload = json.loads(raw) if raw.lstrip().startswith(("{", "[")) else yaml.safe_load(raw)
        except (ValueError, yaml.YAMLError) as exc:
            raise ServiceError("QA_SPEC_INVALID", "OpenAPI JSON/YAML inválido.") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("paths"), dict):
            raise ServiceError("QA_SPEC_INVALID", "Documento não contém paths do OpenAPI.")
        return payload

    @staticmethod
    def discover_openapi(spec: Dict[str, Any], base_url: Optional[str] = None) -> List[Dict[str, Any]]:
        detected_base = base_url
        if not detected_base:
            servers = spec.get("servers") or []
            if servers and isinstance(servers[0], dict):
                detected_base = servers[0].get("url")
        endpoints = []
        for path, operations in spec.get("paths", {}).items():
            if not isinstance(operations, dict):
                continue
            for method, operation in operations.items():
                if method.lower() not in OPENAPI_METHODS or not isinstance(operation, dict):
                    continue
                endpoint: Dict[str, Any] = {
                    "method": method.upper(),
                    "path": str(path),
                    "source": "openapi",
                    "operation_id": operation.get("operationId"),
                    "summary": operation.get("summary"),
                    "security": bool(operation.get("security", spec.get("security"))),
                    "parameters": [
                        {"name": item.get("name"), "in": item.get("in"), "required": item.get("required", False)}
                        for item in operation.get("parameters", [])
                        if isinstance(item, dict)
                    ],
                    "expected_status": [
                        int(code)
                        for code in operation.get("responses", {})
                        if str(code).isdigit() and 100 <= int(code) <= 599
                    ][:20],
                }
                if detected_base:
                    endpoint["url"] = urljoin(detected_base.rstrip("/") + "/", str(path).lstrip("/"))
                endpoints.append(endpoint)
        return endpoints

    @staticmethod
    def generate_plan(
        endpoints: List[Dict[str, Any]], suite_name: str, base_url: Optional[str], include_mutating: bool
    ) -> Dict[str, Any]:
        cases = []
        skipped = []
        for index, endpoint in enumerate(endpoints, 1):
            method = str(endpoint.get("method", "GET")).upper()
            target = endpoint.get("url") or endpoint.get("path")
            if not target or method not in HTTP_METHODS:
                continue
            if method not in SAFE_METHODS and not include_mutating:
                skipped.append({"method": method, "target": target, "reason": "mutating_manual_review"})
                continue
            case: Dict[str, Any] = {
                "id": f"generated-{index}",
                "name": endpoint.get("summary") or f"{method} {endpoint.get('path', target)}",
                "method": method,
                "expected_status": endpoint.get("expected_status") or (
                    [200] if method in SAFE_METHODS else [200, 201, 202, 204]
                ),
                "allow_mutating": method not in SAFE_METHODS,
                "tags": ["generated", str(endpoint.get("source", "discovery"))],
            }
            case["url" if str(target).startswith(("http://", "https://")) else "path"] = target
            cases.append(case)
        return {
            "suite": {
                "name": suite_name,
                "base_url": base_url,
                "cases": cases,
                "concurrency": 4,
                "stop_on_failure": False,
            },
            "skipped": skipped,
            "review_required": bool(skipped) or any("{" in str(c.get("path", "")) for c in cases),
        }

    async def execute_case(
        self, case: QaCase, base_url: Optional[str] = None, variables: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        values = variables or {}
        raw = _replace_variables(case.model_dump(), values)
        target = raw.get("url") or urljoin((base_url or "").rstrip("/") + "/", raw["path"].lstrip("/"))
        method = raw["method"]
        self.policy.check_qa(target, method, raw.get("allow_mutating", False))
        started = time.perf_counter()
        try:
            response = await self.client.request(
                method,
                target,
                headers=raw.get("headers"),
                params=raw.get("query"),
                json=raw.get("json_body") if raw.get("json_body") is not None else None,
                timeout=raw["timeout_ms"] / 1000,
            )
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
        except httpx.TimeoutException as exc:
            return self._error_result(case, target, "timeout", str(exc), started)
        except httpx.HTTPError as exc:
            return self._error_result(case, target, "network_error", type(exc).__name__, started)
        content_type = response.headers.get("content-type", "")
        body_bytes = response.content[:262144]
        body_text = body_bytes.decode(response.encoding or "utf-8", errors="replace")
        try:
            json_payload = response.json() if "json" in content_type.lower() else None
        except ValueError:
            json_payload = None
        assertions = [QaAssertion(kind="status", expected=raw["expected_status"])] + case.assertions
        checks = [self._assert(assertion, response, body_text, json_payload, duration_ms) for assertion in assertions]
        passed = all(check["passed"] for check in checks)
        return {
            "case_id": case.id,
            "name": case.name,
            "status": "passed" if passed else "failed",
            "method": method,
            "url": redact_url(str(response.request.url)),
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "assertions": checks,
            "evidence": {
                "response_headers": redact(dict(response.headers)),
                "body_preview": redact_body(_redact_html_tokens(body_text[:8192]), content_type),
                "body_truncated": len(response.content) > len(body_bytes),
                "content_type": content_type,
            },
        }

    @staticmethod
    def _error_result(case: QaCase, target: str, code: str, detail: str, started: float) -> Dict[str, Any]:
        return {
            "case_id": case.id,
            "name": case.name,
            "status": "error",
            "method": case.method,
            "url": redact_url(target),
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "error": {"code": code, "detail": detail[:200]},
            "assertions": [],
        }

    @staticmethod
    def _assert(
        assertion: QaAssertion,
        response: httpx.Response,
        body: str,
        payload: Any,
        duration_ms: float,
    ) -> Dict[str, Any]:
        kind, key, expected = assertion.kind, assertion.key, assertion.expected
        actual: Any = None
        try:
            if kind == "status":
                actual = response.status_code
                passed = actual in list(expected)
            elif kind == "header_exists":
                actual = key in response.headers
                passed = actual is True
            elif kind == "header_equals":
                actual = response.headers.get(key or "")
                passed = actual == expected
            elif kind == "body_contains":
                actual = str(expected) in body
                passed = actual is True
            elif kind == "json_path_equals":
                actual = _json_path(payload, key or "")
                passed = actual == expected
            elif kind == "response_time_ms":
                actual = duration_ms
                passed = duration_ms <= float(expected)
            else:
                required = list(expected or [])
                actual = list(payload) if isinstance(payload, dict) else []
                passed = isinstance(payload, dict) and all(item in payload for item in required)
        except (KeyError, TypeError, ValueError, IndexError):
            passed = False
            actual = None
        return {"kind": kind, "key": key, "expected": redact(expected), "actual": redact(actual), "passed": passed}

    async def run_suite(self, suite: QaSuite, variables: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        run_id = uuid.uuid4().hex
        started = time.time()
        merged = {**suite.variables, **(variables or {})}
        semaphore = asyncio.Semaphore(suite.concurrency)

        async def run(case: QaCase) -> Dict[str, Any]:
            async with semaphore:
                return await self.execute_case(case, suite.base_url, merged)

        results: List[Dict[str, Any]] = []
        if suite.stop_on_failure:
            for case in suite.cases:
                result = await run(case)
                results.append(result)
                if result["status"] != "passed":
                    break
        else:
            results = await asyncio.gather(*(run(case) for case in suite.cases))
        summary = self._summary(results)
        report = {
            "run_id": run_id,
            "suite": suite.name,
            "status": "passed" if summary["failed"] == 0 and summary["errors"] == 0 else "failed",
            "started_at": started,
            "completed_at": time.time(),
            "summary": summary,
            "results": results,
        }
        self._save_run(report)
        return report

    @staticmethod
    def _summary(results: List[Dict[str, Any]]) -> Dict[str, Any]:
        durations = [float(item.get("duration_ms", 0)) for item in results]
        return {
            "total": len(results),
            "passed": sum(item["status"] == "passed" for item in results),
            "failed": sum(item["status"] == "failed" for item in results),
            "errors": sum(item["status"] == "error" for item in results),
            "duration_ms": round(sum(durations), 2),
            "slowest_ms": round(max(durations, default=0), 2),
        }

    def _save_run(self, report: Dict[str, Any]) -> None:
        path = self.runs_root / f"{report['run_id']}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def load_run(self, run_id: Optional[str]) -> Dict[str, Any]:
        if run_id:
            if not re.fullmatch(r"[a-f0-9]{32}", run_id):
                raise ServiceError("QA_RUN_NOT_FOUND", "Identificador de execução inválido.")
            path = self.runs_root / f"{run_id}.json"
        else:
            candidates = sorted(self.runs_root.glob("*.json"), key=lambda item: item.stat().st_mtime)
            if not candidates:
                raise ServiceError("QA_RUN_NOT_FOUND", "Nenhuma execução QA encontrada.")
            path = candidates[-1]
        if not path.is_file():
            raise ServiceError("QA_RUN_NOT_FOUND", "Execução QA não encontrada.")
        return json.loads(path.read_text(encoding="utf-8"))

    def list_runs(self, limit: int) -> List[Dict[str, Any]]:
        rows = []
        paths = sorted(self.runs_root.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
        for path in paths[:limit]:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                rows.append({key: data.get(key) for key in ("run_id", "suite", "status", "started_at", "completed_at", "summary")})
            except (OSError, ValueError):
                continue
        return rows

    def export_report(self, report: Dict[str, Any], fmt: str, output_path: Optional[str]) -> Dict[str, Any]:
        if fmt == "json":
            return report
        content = self._html(report) if fmt == "html" else self._junit(report)
        suffix = ".html" if fmt == "html" else ".xml"
        path = Path(output_path).expanduser().resolve() if output_path else self.runs_root / f"{report['run_id']}{suffix}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {"run_id": report["run_id"], "format": fmt, "path": str(path), "content": content}

    @staticmethod
    def _html(report: Dict[str, Any]) -> str:
        cards = []
        for result in report["results"]:
            assertions = "".join(
                f"<li class='{('ok' if item['passed'] else 'bad')}'>{html.escape(item['kind'])}: "
                f"{html.escape(str(item.get('actual')))}</li>" for item in result.get("assertions", [])
            )
            cards.append(
                f"<article><h3>{html.escape(result['name'])}</h3><p><b>{result['method']}</b> "
                f"{html.escape(result['url'])} — {html.escape(result['status'])} ({result['duration_ms']} ms)</p>"
                f"<ul>{assertions}</ul></article>"
            )
        summary = report["summary"]
        return "<!doctype html><html><head><meta charset='utf-8'><title>Achilles QA</title><style>" \
            "body{font:15px system-ui;background:#0b0d12;color:#eef2ff;max-width:1100px;margin:auto;padding:32px}" \
            "article{background:#151924;border:1px solid #293044;border-radius:12px;padding:16px;margin:12px 0}" \
            ".ok{color:#74e0a7}.bad{color:#ff7b91}code{color:#9bbcff}</style></head><body>" \
            f"<h1>Achilles QA — {html.escape(report['suite'])}</h1><p>Run <code>{report['run_id']}</code> · " \
            f"{summary['passed']} passaram · {summary['failed']} falharam · {summary['errors']} erros</p>" \
            + "".join(cards) + "</body></html>"

    @staticmethod
    def _junit(report: Dict[str, Any]) -> str:
        summary = report["summary"]
        cases = []
        for result in report["results"]:
            failure = ""
            if result["status"] != "passed":
                failure = f"<failure message='{html.escape(result['status'])}'>{html.escape(json.dumps(result.get('assertions', []), ensure_ascii=False))}</failure>"
            cases.append(
                f"<testcase classname='{html.escape(report['suite'])}' name='{html.escape(result['name'])}' time='{float(result.get('duration_ms', 0))/1000:.3f}'>{failure}</testcase>"
            )
        return "<?xml version='1.0' encoding='UTF-8'?><testsuite " \
            f"name='{html.escape(report['suite'])}' tests='{summary['total']}' failures='{summary['failed']}' errors='{summary['errors']}'>" \
            + "".join(cases) + "</testsuite>"
