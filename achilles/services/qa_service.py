"""Fachada de QA compartilhada por agentes, CLI, REST e Studio."""

import json
from pathlib import Path
from typing import Any, Dict, List

import yaml

from .errors import ServiceError
from .policy import PolicyEngine
from .qa_contracts import QaCase, QaSuite
from .qa_engine import QaEngine
from .traffic_journal import TrafficJournal


class QaService:
    def __init__(self, journal: TrafficJournal, policy: PolicyEngine) -> None:
        self.journal = journal
        self.policy = policy
        self.engine = QaEngine(policy)

    async def call(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if name == "qa_status":
            qa = self.policy.config.get("qa", {})
            return {
                "available": True,
                "engine": "httpx",
                "studio": True,
                "openapi": True,
                "reports": ["json", "html", "junit"],
                "safe_methods": ["GET", "HEAD", "OPTIONS"],
                "allowed_hosts": qa.get("allow_hosts", ["localhost", "127.0.0.1", "::1"]),
                "mutating_enabled": bool(qa.get("allow_mutating_methods", False)),
            }
        if name == "qa_discover":
            endpoints: List[Dict[str, Any]] = []
            sources = []
            if args.get("include_traffic"):
                endpoints.extend(self.engine.discover_traffic(self.journal.records, args.get("page_id"), args["limit"]))
                sources.append("traffic")
            if args.get("openapi"):
                spec = await self.engine.load_openapi(args["openapi"])
                endpoints.extend(self.engine.discover_openapi(spec, args.get("base_url")))
                sources.append("openapi")
            unique = {(item["method"], item.get("url") or item.get("path")): item for item in endpoints}
            rows = list(unique.values())
            return {"sources": sources, "endpoints": rows, "count": len(rows)}
        if name == "qa_plan":
            return self.engine.generate_plan(**args)
        if name == "qa_request":
            case = QaCase(name=f"{args['method']} {args['url']}", **args)
            return await self.engine.execute_case(case)
        if name == "qa_run_suite":
            suite = args.get("suite")
            if suite is None:
                suite = self._load_suite(args["path"])
            elif isinstance(suite, QaSuite):
                pass
            else:
                suite = QaSuite.model_validate(suite)
            return await self.engine.run_suite(suite, args.get("variables"))
        if name == "qa_report":
            report = self.engine.load_run(args.get("run_id"))
            return self.engine.export_report(report, args["format"], args.get("output_path"))
        if name == "qa_runs":
            rows = self.engine.list_runs(args["limit"])
            return {"runs": rows, "count": len(rows)}
        if name == "qa_security_audit":
            return await self._security_audit(args)
        raise ServiceError("UNKNOWN_TOOL", "Ferramenta QA desconhecida.")

    @staticmethod
    def _load_suite(source: str) -> QaSuite:
        path = Path(source).expanduser().resolve()
        if not path.is_file() or path.stat().st_size > 1024 * 1024:
            raise ServiceError("QA_SUITE_NOT_FOUND", "Suíte inexistente ou maior que 1 MiB.")
        raw = path.read_text(encoding="utf-8")
        try:
            payload = json.loads(raw) if path.suffix.casefold() == ".json" else yaml.safe_load(raw)
            return QaSuite.model_validate(payload)
        except (ValueError, yaml.YAMLError) as exc:
            raise ServiceError("QA_SUITE_INVALID", "Suíte JSON/YAML inválida.") from exc

    async def _security_audit(self, args: Dict[str, Any]) -> Dict[str, Any]:
        urls = list(args.get("urls", []))
        if args.get("include_traffic"):
            urls.extend(
                item["url"]
                for item in self.engine.discover_traffic(
                    self.journal.records, args.get("page_id"), 200
                )
            )
        urls = list(dict.fromkeys(urls))[:50]
        if not urls:
            raise ServiceError("QA_TARGET_REQUIRED", "Informe urls ou capture tráfego antes da auditoria.")
        findings: List[Dict[str, Any]] = []
        coverage = []
        for url in urls:
            case = QaCase(
                name=f"Security headers {url}", method="GET", url=url,
                expected_status=[
                    200, 201, 202, 204, 301, 302, 400, 401,
                    403, 404, 405, 429, 500, 502, 503,
                ],
                timeout_ms=args["timeout_ms"],
            )
            result = await self.engine.execute_case(case)
            coverage.append({"url": result["url"], "status": result["status"], "status_code": result.get("status_code")})
            headers = result.get("evidence", {}).get("response_headers", {})
            findings.extend(self._header_findings(result["url"], headers))
        weights = {"high": 20, "medium": 10, "low": 3}
        return {
            "mode": "defensive_non_exploitative",
            "findings": findings,
            "summary": {
                "targets": len(urls),
                "total_findings": len(findings),
                "risk_score": min(100, sum(weights[item["severity"]] for item in findings)),
            },
            "coverage": coverage,
            "not_tested": ["authorization_exploitation", "injection_payloads", "load_testing", "database_integrity"],
        }

    @staticmethod
    def _header_findings(url: str, headers: Dict[str, Any]) -> List[Dict[str, Any]]:
        normalized = {str(key).lower(): str(value) for key, value in headers.items()}
        findings = []

        def add(rule: str, severity: str, title: str, evidence: str, remediation: str) -> None:
            findings.append({"rule_id": rule, "severity": severity, "title": title, "url": url, "evidence": evidence, "remediation": remediation})

        content_type = normalized.get("content-type", "")
        if "text/html" in content_type and "content-security-policy" not in normalized:
            add("CSP_MISSING", "medium", "CSP ausente", "Header não observado", "Defina Content-Security-Policy adequada.")
        if url.startswith("https://") and "strict-transport-security" not in normalized:
            add("HSTS_MISSING", "low", "HSTS ausente", "Resposta HTTPS sem HSTS", "Habilite HSTS após validar subdomínios.")
        if normalized.get("access-control-allow-origin") == "*":
            add("CORS_WILDCARD", "medium", "CORS permite qualquer origem", "Access-Control-Allow-Origin: *", "Restrinja as origens necessárias.")
        if "x-content-type-options" not in normalized:
            add("NOSNIFF_MISSING", "low", "Proteção MIME ausente", "X-Content-Type-Options não observado", "Configure nosniff.")
        if "server" in normalized:
            add("SERVER_DISCLOSURE", "low", "Servidor exposto em header", f"Server: {normalized['server'][:80]}", "Remova versões e detalhes desnecessários.")
        cookies = normalized.get("set-cookie", "")
        if cookies and "secure" not in cookies.casefold() and url.startswith("https://"):
            add("COOKIE_SECURE_MISSING", "medium", "Cookie sem Secure", "Set-Cookie observado sem Secure", "Use Secure em cookies sensíveis.")
        return findings

    async def close(self) -> None:
        await self.engine.close()
