"""Auditoria passiva com evidência, cobertura explícita e confiança ponderada."""

import base64
import json
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from .redaction import SECRETS, mask, redact_url
from .session_manager import BrowserSessionManager
from .traffic_journal import TrafficJournal


class SecurityAuditEngine:
    WEIGHTS = {"critical": 35, "high": 20, "medium": 10, "low": 3}

    def __init__(self, session: BrowserSessionManager, journal: TrafficJournal) -> None:
        self.session = session
        self.journal = journal

    @staticmethod
    def inspect_jwt(token: str) -> Dict[str, Any]:
        try:
            parts = token.split(".")
            if len(parts) != 3 or len(token) > 32768:
                return {"decoded": False, "signature_verified": False, "issues": []}
            header, payload = [
                json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4))) for p in parts[:2]
            ]
            if not isinstance(header, dict) or not isinstance(payload, dict):
                raise ValueError("JWT objects required")
            issues = []
            if str(header.get("alg", "")).lower() == "none":
                issues.append("unsigned_jwt")
            if "exp" not in payload:
                issues.append("missing_expiration")
            if (
                payload.get("role") in ("service_role", "admin", "administrator")
                or payload.get("is_admin") is True
            ):
                issues.append("administrative_claim")
            return {"decoded": True, "signature_verified": False, "issues": issues}
        except (ValueError, TypeError, UnicodeError):
            return {"decoded": False, "signature_verified": False, "issues": []}

    @classmethod
    def analyze(
        cls,
        url: str,
        response_headers: Optional[Dict[str, str]],
        cookies: List[Dict[str, Any]],
        storage: Dict[str, Any],
        records: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        findings: List[Dict[str, Any]] = []
        seen = set()

        def add(
            rule: str, severity: str, confidence: float, title: str, evidence: str, remediation: str
        ) -> None:
            identity = (rule, evidence)
            if identity in seen:
                return
            seen.add(identity)
            findings.append(
                {
                    "rule_id": rule,
                    "severity": severity,
                    "confidence": confidence,
                    "title": title,
                    "evidence": evidence,
                    "remediation": remediation,
                }
            )

        if response_headers is not None:
            h = {k.lower(): v for k, v in response_headers.items()}
            if "content-security-policy" not in h:
                add(
                    "CSP_MISSING",
                    "medium",
                    0.8,
                    "CSP ausente no header da resposta capturada",
                    "Content-Security-Policy não observado; política via meta não avaliada.",
                    "Defina CSP apropriada para o documento.",
                )
            if urlsplit(url).scheme == "https" and "strict-transport-security" not in h:
                add(
                    "HSTS_MISSING",
                    "low",
                    0.9,
                    "HSTS ausente",
                    "Resposta HTTPS sem HSTS.",
                    "Configure HSTS após validar HTTPS e subdomínios.",
                )
            if (
                "x-frame-options" not in h
                and "frame-ancestors" not in h.get("content-security-policy", "").lower()
            ):
                add(
                    "FRAME_PROTECTION_MISSING",
                    "medium",
                    0.7,
                    "Proteção de enquadramento ausente",
                    "X-Frame-Options e CSP frame-ancestors não observados.",
                    "Configure CSP frame-ancestors conforme integrações permitidas.",
                )

        for r in records:
            headers = {k.lower(): v for k, v in r.get("response_headers", {}).items()}
            req_headers = {k.lower(): v for k, v in r.get("request_headers", {}).items()}
            origin = req_headers.get("origin")
            allowed = headers.get("access-control-allow-origin")
            credentials = headers.get("access-control-allow-credentials", "").lower() == "true"
            if origin and allowed == origin and credentials:
                add(
                    "CORS_REFLECTION_CANDIDATE",
                    "low",
                    0.35,
                    "Origin coincidente com credentials",
                    f"Exchange {r.get('request_id', 'unknown')}; não prova reflexão arbitrária.",
                    "Confirme allowlist no servidor; coincidência com origem autorizada é legítima.",
                )
            if allowed == "*" and credentials:
                add(
                    "CORS_INVALID_CREDENTIALS",
                    "low",
                    1.0,
                    "CORS wildcard incompatível com credentials",
                    f"Exchange {r.get('request_id', 'unknown')}",
                    "Configure origem explícita; o navegador bloqueia leitura credentialed com wildcard.",
                )

        for cookie in cookies:
            name = str(cookie.get("name", ""))
            if not any(s in name.lower() for s in ("session", "auth", "token", "jwt", "sid")):
                continue
            for flag in ("httpOnly", "secure"):
                if not cookie.get(flag) and (flag != "secure" or urlsplit(url).scheme == "https"):
                    add(
                        "COOKIE_" + flag.upper(),
                        "medium",
                        0.8,
                        f"Cookie de sessão sem {flag}",
                        mask(name),
                        f"Revise flag {flag} no cookie de sessão.",
                    )
            if cookie.get("sameSite") == "None" and not cookie.get("secure"):
                add(
                    "COOKIE_SAMESITE",
                    "medium",
                    1.0,
                    "SameSite=None sem Secure",
                    mask(name),
                    "Use Secure com SameSite=None.",
                )

        sources = [("storage", json.dumps(storage, ensure_ascii=False))]
        for record in records:
            sources.append(
                (
                    "exchange:" + str(record.get("request_id", "unknown")),
                    json.dumps(
                        {
                            k: record.get(k)
                            for k in (
                                "url",
                                "request_headers",
                                "response_headers",
                                "request_body",
                                "response_body",
                            )
                        },
                        ensure_ascii=False,
                    ),
                )
            )
        for source, text in sources:
            for match in SECRETS.finditer(text):
                token = match.group()
                evidence = f"{source}: {mask(token)}"
                if token.startswith("eyJ"):
                    jwt = cls.inspect_jwt(token)
                    for issue in jwt["issues"]:
                        severity = "high" if issue == "unsigned_jwt" else "medium"
                        add(
                            "JWT_" + issue.upper(),
                            severity,
                            0.9,
                            issue,
                            evidence,
                            "Revise emissão e validação no servidor; decodificação não comprova aceitação do token.",
                        )
                else:
                    add(
                        "CLIENT_SECRET",
                        "critical",
                        0.9,
                        "Credencial privada observada no cliente",
                        evidence,
                        "Confirme a credencial, rotacione-a e mova seu uso para o servidor.",
                    )
        score = min(100, round(sum(cls.WEIGHTS[f["severity"]] * f["confidence"] for f in findings)))
        return {
            "page_url": redact_url(url),
            "mode": "passive",
            "findings": findings,
            "summary": {
                "risk_score": score,
                "total_findings": len(findings),
                "formula": "min(100, sum(severity_weight * confidence))",
            },
            "coverage": {
                "navigation_response_headers": "observed"
                if response_headers is not None
                else "not_observed",
                "authorization_exploitation": "not_tested",
                "database_integrity": "not_tested",
            },
        }

    async def audit(self, page_id: Optional[str] = None) -> Dict[str, Any]:
        key, page = await self.session.page(page_id)
        async with self.session.registry.locks[key]:
            await self.session.drain()
            storage: Dict[str, Any] = {}
            skipped = []
            for frame in list(page.frames)[:64]:
                frame_id = self.session.registry.frame_id(frame)
                try:
                    storage[frame_id] = await frame.evaluate("""() => {
                        const read = store => { const out = {}; let bytes = 0;
                            for (let i=0; i<Math.min(store.length,200); i++) {
                                const k=store.key(i), v=store.getItem(k) || '';
                                if ((bytes += v.length) > 262144) break; out[k]=v.slice(0,32768);
                            } return out; };
                        return {local:read(localStorage),session:read(sessionStorage)};
                    }""")
                except Exception:
                    skipped.append(frame_id)
            cookies = [dict(cookie) for cookie in await page.context.cookies([page.url])]
            navigation = self.journal.navigation(key, page.url)
            records = [r for r in self.journal.records if r["page_id"] == key]
            result = self.analyze(
                page.url,
                navigation["response_headers"] if navigation else None,
                cookies,
                storage,
                records,
            )
            result["coverage"]["storage_skipped_frames"] = skipped
            result["coverage"]["storage_limits"] = {
                "keys_per_store": 200,
                "characters_per_store": 262144,
            }
            return result
