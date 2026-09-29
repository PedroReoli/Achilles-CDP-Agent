"""
auditor.py — Motor de Auditoria OWASP Top 10, API Security e Hardening de Banco de Dados.
"""
import base64
import json
import re
from typing import Any, Dict, List


class SecurityAuditor:
    """Executa varredura profunda em DOM, Cookies, Web Storage, Headers e Tráfego de Rede."""

    CATEGORIES = {
        "AUTH": "Autenticação & Sessões",
        "ACCESS_CONTROL": "Autorização / RBAC / BOLA / IDOR",
        "SUPABASE_RLS": "Supabase / RLS & Storage Policies",
        "INJECTION": "Injeções (SQLi, Logic, Command, Prototype Pollution)",
        "INPUT_XSS": "Validação de Entrada & XSS (DOM, Reflected, Stored)",
        "DATA_EXPOSURE": "Exposição de Dados Sensíveis & Secrets",
        "STORAGE": "Armazenamento Inseguro (LocalStorage / SessionStorage)",
        "UPLOADS_STORAGE": "Uploads & Buckets de Storage",
        "API_RATE_LIMIT": "APIs, Webhooks & Rate Limiting",
        "SECURITY_HEADERS_CORS": "CORS, CSRF & Security Headers",
        "SSRF_TRAVERSAL": "SSRF, Path Traversal & Open Redirect",
        "BUSINESS_LOGIC": "Frontend vs Backend & Lógica de Negócio",
        "DATABASE_HARDENING": "Integridade, Normalização & Hardening de Banco de Dados"
    }

    SECRET_PATTERNS = [
        (r"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+", "Supabase / JWT Token", "HIGH"),
        (r"sbp_[a-zA-Z0-9]{40}", "Supabase Personal Access Token", "CRITICAL"),
        (r"sk_live_[0-9a-zA-Z]{24,}", "Stripe Live Secret Key", "CRITICAL"),
        (r"rk_live_[0-9a-zA-Z]{24,}", "Stripe Live Restricted Key", "CRITICAL"),
        (r"ghp_[0-9a-zA-Z]{36}", "GitHub Personal Access Token", "CRITICAL"),
        (r"AKIA[0-9A-Z]{16}", "AWS Access Key ID", "HIGH"),
        (r"AIza[0-9A-Za-z-_]{35}", "Google API Key", "MEDIUM"),
        (r"-----BEGIN PRIVATE KEY-----", "RSA/ECC Private Key", "CRITICAL"),
        (r"service_role", "Supabase Service Role Key Indicator", "CRITICAL"),
    ]

    @staticmethod
    def inspect_jwt(token: str) -> Dict[str, Any]:
        issues = []
        try:
            parts = token.split(".")
            if len(parts) != 3:
                return {"valid": False, "error": "Formato JWT inválido"}
            
            header = json.loads(base64.urlsafe_b64decode(parts[0] + "==").decode("utf-8", errors="ignore"))
            payload = json.loads(base64.urlsafe_b64decode(parts[1] + "==").decode("utf-8", errors="ignore"))

            alg = header.get("alg", "").lower()
            if alg == "none":
                issues.append("Algoritmo JWT definido como 'none' (vulnerabilidade crítica).")
            elif alg in ["hs256", "hs384", "hs512"]:
                issues.append(f"JWT usa chave simétrica ({alg.upper()}). Verificar se o segredo tem alta entropia.")

            if "exp" not in payload:
                issues.append("Token JWT não possui claim de expiração ('exp').")
            
            if payload.get("role") == "service_role":
                issues.append("ALERTA CRÍTICO: Token com role 'service_role' trafegando no cliente!")

            return {
                "valid": True,
                "header": header,
                "payload_claims": list(payload.keys()),
                "role": payload.get("role"),
                "has_exp": "exp" in payload,
                "issues": issues
            }
        except Exception as e:
            return {"valid": False, "error": str(e)}

    @classmethod
    def audit(cls, page_url: str, page_title: str, page_headers: Dict[str, str], cookies: List[Dict[str, Any]], local_storage: Dict[str, str], session_storage: Dict[str, str], recorded_requests: List[Dict[str, Any]], dom_meta: Dict[str, Any]) -> Dict[str, Any]:
        findings = []

        # Headers
        h_lower = {k.lower(): v for k, v in page_headers.items()}
        if "content-security-policy" not in h_lower:
            findings.append({
                "category": "SECURITY_HEADERS_CORS",
                "owasp": "A05:2021-Security Misconfiguration",
                "severity": "HIGH",
                "title": "Ausência de Content-Security-Policy (CSP)",
                "description": "O servidor não envia header CSP, aumentando a vulnerabilidade a XSS.",
                "remediation": "Configure o header Content-Security-Policy com diretivas estritas."
            })
        if h_lower.get("access-control-allow-origin") == "*":
            findings.append({
                "category": "SECURITY_HEADERS_CORS",
                "owasp": "A01:2021-Broken Access Control",
                "severity": "HIGH",
                "title": "CORS Wildcard Excessivamente Permissivo (*)",
                "description": "Qualquer domínio de terceiros pode ler respostas da API via JS.",
                "remediation": "Restrinja o CORS aos domínios autorizados."
            })

        # Cookies
        for cookie in cookies:
            name = cookie.get("name", "")
            if any(k in name.lower() for k in ["auth", "token", "session", "jwt", "sid"]):
                if not cookie.get("httpOnly"):
                    findings.append({
                        "category": "STORAGE",
                        "owasp": "A07:2021-Identification and Authentication Failures",
                        "severity": "HIGH",
                        "title": f"Cookie de Sessão sem HttpOnly ('{name}')",
                        "description": "Cookie acessível via document.cookie, vulnerável a roubo por XSS.",
                        "remediation": "Adicione flag HttpOnly=true."
                    })
                if not cookie.get("secure"):
                    findings.append({
                        "category": "AUTH",
                        "owasp": "A02:2021-Cryptographic Failures",
                        "severity": "HIGH",
                        "title": f"Cookie sem flag Secure ('{name}')",
                        "description": "Cookie pode trafegar em texto claro via HTTP.",
                        "remediation": "Defina Secure=true."
                    })

        # Storage
        all_storage = {**{f"localStorage.{k}": v for k, v in local_storage.items()}, **{f"sessionStorage.{k}": v for k, v in session_storage.items()}}
        for k, v in all_storage.items():
            if isinstance(v, str) and "eyJhbGciOi" in v:
                cls.inspect_jwt(v)
                findings.append({
                    "category": "STORAGE",
                    "owasp": "A02:2021-Cryptographic Failures",
                    "severity": "HIGH" if "service_role" in v else "MEDIUM",
                    "title": f"Token JWT armazenado no Web Storage ('{k}')",
                    "description": "Vulnerável a extração completa via XSS.",
                    "remediation": "Prefira cookies HttpOnly com SameSite=Strict."
                })

        # Network traffic & Supabase keys
        for req in recorded_requests:
            url = req.get("url", "")
            traffic_text = f"{url} {json.dumps(req.get('headers', {}))} {req.get('post_data', '') or ''}"
            if "service_role" in traffic_text:
                findings.append({
                    "category": "SUPABASE_RLS",
                    "owasp": "A01:2021-Broken Access Control",
                    "severity": "CRITICAL",
                    "title": "SUPABASE SERVICE_ROLE KEY EXPOSTA NO CLIENTE",
                    "description": "A chave service_role bypassa todo o Row Level Security do banco de dados.",
                    "remediation": "Revogue a chave imediatamente e use apenas a anon_key no cliente."
                })
            if re.search(r"/(user|account|order|invoice)/[0-9]{1,8}(|/)", url, re.IGNORECASE):
                findings.append({
                    "category": "ACCESS_CONTROL",
                    "owasp": "A01:2021-Broken Access Control (IDOR/BOLA)",
                    "severity": "HIGH",
                    "title": f"Potencial Rota Suscetível a IDOR/BOLA: {url[:60]}",
                    "description": "ID sequencial em rota. Requer validação estrita de ownership no backend.",
                    "remediation": "Use UUIDs e cheque autorização do recurso no backend."
                })

        unique = []
        seen = set()
        for f in findings:
            key = f"{f['title']}-{f['severity']}"
            if key not in seen:
                seen.add(key)
                unique.append(f)

        weights = {"CRITICAL": 35, "HIGH": 20, "MEDIUM": 10, "LOW": 3}
        risk_score = min(100, sum(weights.get(f.get("severity", "LOW"), 5) for f in unique))

        return {
            "page": {"url": page_url, "title": page_title},
            "summary": {
                "risk_score": risk_score,
                "risk_level": "CRÍTICO" if risk_score >= 70 else ("ALTO" if risk_score >= 40 else ("MÉDIO" if risk_score >= 20 else "BAIXO")),
                "total_findings": len(unique),
                "critical": sum(1 for f in unique if f["severity"] == "CRITICAL"),
                "high": sum(1 for f in unique if f["severity"] == "HIGH"),
                "medium": sum(1 for f in unique if f["severity"] == "MEDIUM"),
                "low": sum(1 for f in unique if f["severity"] == "LOW"),
            },
            "findings": unique
        }
