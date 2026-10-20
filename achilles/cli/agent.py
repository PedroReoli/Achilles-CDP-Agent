"""Superfície CLI estável e estruturada para agentes e scripts."""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict

from achilles.services.application import ApplicationServices
from achilles.services.errors import ServiceError


def parse_arguments(value: str) -> Dict[str, Any]:
    if value == "-":
        raw = sys.stdin.read()
    elif value.startswith("@"):
        raw = Path(value[1:]).read_text(encoding="utf-8")
    else:
        raw = value
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("--arguments deve representar um objeto JSON")
    return parsed


def call_api(api_url: str, token: str, tool: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    endpoint = api_url.rstrip("/") + "/api/tools/" + urllib.parse.quote(tool, safe="")
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(arguments).encode("utf-8"),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=95) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(body)
        except ValueError:
            detail = {"message": body or exc.reason}
        raise ServiceError("REMOTE_ERROR", json.dumps(detail, ensure_ascii=False)) from None
    except urllib.error.URLError as exc:
        raise ServiceError("API_UNAVAILABLE", str(exc.reason), retryable=True) from None


async def run_call(
    cdp_port: int,
    tool: str,
    arguments_value: str,
    api_url: str = "",
    token: str = "",
) -> None:
    services = None
    try:
        arguments = parse_arguments(arguments_value)
        if api_url:
            access_token = token or os.environ.get("ACHILLES_API_TOKEN", "")
            if not access_token:
                raise ServiceError(
                    "TOKEN_REQUIRED",
                    "Defina ACHILLES_API_TOKEN para usar --api-url.",
                )
            import asyncio

            result = await asyncio.to_thread(call_api, api_url, access_token, tool, arguments)
        else:
            services = ApplicationServices(cdp_port)
            result = await services.call(tool, arguments)
        print(json.dumps({"ok": True, "tool": tool, "result": result}, ensure_ascii=False))
    except (ValueError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {"ok": False, "error": {"code": "INVALID_JSON", "message": str(exc)}},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        raise SystemExit(2) from None
    except ServiceError as exc:
        print(json.dumps({"ok": False, "error": exc.as_dict()}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1) from None
    finally:
        if services is not None:
            await services.close()
