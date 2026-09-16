"""Redação recursiva usada antes de qualquer exportação."""

import hashlib
import json
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SENSITIVE = re.compile(
    r"authorization|cookie|token|secret|password|passwd|api[-_]?key|credential|x-api-key|stripe-signature|aws-sigv4", re.I
)
ASSIGNMENT = re.compile(
    r"""(?i)((?:password|passwd|token|secret|api[_-]?key|stripe-signature|aws-sigv4)["']?\s*[:=]\s*["']?)([^\s"'&,;}]+)"""
)
SECRETS = re.compile(
    r"(?:sbp_[A-Za-z0-9]{20,}|sb_secret_[A-Za-z0-9_-]+|[sr]k_(?:live|test)_[A-Za-z0-9]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*|AKIA[0-9A-Z]{16})"
)


def mask(value: str) -> str:
    prefix = value[:8] if value.startswith(("sbp_", "sb_secret_")) else "[REDACTED]"
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}... [sha256:{digest}]"


def redact(value: Any, key: str = "") -> Any:
    if SENSITIVE.search(key) and value is not None:
        return mask(str(value))
    if isinstance(value, dict):
        return {str(k): redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [redact(v) for v in value]
    if isinstance(value, str):
        if value.startswith(("https://", "http://")):
            return redact_url(value)
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            parsed = None
        if isinstance(parsed, (dict, list)):
            return json.dumps(redact(parsed), ensure_ascii=False)
        text = SECRETS.sub(lambda m: mask(m.group()), value)
        return ASSIGNMENT.sub(lambda m: m.group(1) + mask(m.group(2)), text)
    return value


def redact_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        host = parts.netloc.rsplit("@", 1)[-1]
        query = urlencode(
            [(k, redact(v, k)) for k, v in parse_qsl(parts.query, keep_blank_values=True)]
        )
        return urlunsplit((parts.scheme, host, redact(parts.path), query, redact(parts.fragment)))
    except ValueError:
        return mask(url)


import base64

def redact_body(body: str, content_type: str) -> str:
    if "x-www-form-urlencoded" in content_type:
        return urlencode([(k, redact(v, k)) for k, v in parse_qsl(body, keep_blank_values=True)])
    if "multipart/" in content_type:
        boundary_match = re.search(r"boundary=([\w-]+)", content_type)
        if boundary_match:
            boundary = boundary_match.group(1)
            parts = body.split(boundary)
            redacted_parts = []
            for part in parts:
                if "name=" in part or "filename=" in part:
                    # Verifica se o campo ou conteúdo bate com nossas chaves
                    if SENSITIVE.search(part) or SECRETS.search(part):
                        part = mask(part)
                redacted_parts.append(part)
            return boundary.join(redacted_parts)
        return mask(body)

    # Tenta decodificar Base64
    try:
        # Verifica se parece Base64 e não tem espaços em branco anômalos
        if len(body) > 10 and len(body) % 4 == 0 and re.match(r"^[A-Za-z0-9+/]*={0,2}$", body):
            decoded = base64.b64decode(body).decode('utf-8')
            redacted_decoded = str(redact(decoded))
            if redacted_decoded != decoded:
                return base64.b64encode(redacted_decoded.encode('utf-8')).decode('utf-8')
    except Exception:
        pass

    return str(redact(body))
