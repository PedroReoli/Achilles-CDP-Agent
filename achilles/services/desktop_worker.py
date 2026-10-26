"""Worker stdio isolado para Windows UI Automation."""

import json
import os
import sys
from typing import Any, Dict

from .desktop_protocol import DESKTOP_METHODS, MAX_WORKER_MESSAGE
from .errors import ServiceError
from .policy import PolicyEngine
from .windows_desktop_backend import WindowsDesktopBackend


def _write(payload: Dict[str, Any]) -> None:
    encoded = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
    if len(encoded) > MAX_WORKER_MESSAGE:
        encoded = (
            json.dumps({"id": payload.get("id"), "error": {
                "code": "DESKTOP_RESPONSE_TOO_LARGE",
                "message": "Resposta do worker excedeu 2 MiB.",
                "retryable": False,
            }}, ensure_ascii=False) + "\n"
        ).encode("utf-8")
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


def main() -> None:
    backend = WindowsDesktopBackend(PolicyEngine())
    for raw in sys.stdin.buffer:
        if len(raw) > MAX_WORKER_MESSAGE:
            _write({"id": None, "error": {
                "code": "DESKTOP_REQUEST_TOO_LARGE",
                "message": "Requisição do worker excedeu 2 MiB.",
                "retryable": False,
            }})
            continue
        request_id = None
        try:
            request = json.loads(raw)
            request_id = request.get("id")
            name = request.get("name")
            if name == "shutdown":
                _write({"id": request_id, "result": {"closed": True}})
                return
            if name not in DESKTOP_METHODS or not isinstance(request.get("arguments"), dict):
                raise ServiceError("INVALID_ARGUMENT", "Requisição inválida para o worker.")
            result = getattr(backend, DESKTOP_METHODS[name])(**request["arguments"])
            if name == "app_status":
                result["worker_pid"] = os.getpid()
            _write({"id": request_id, "result": result})
        except ServiceError as exc:
            _write({"id": request_id, "error": exc.as_dict()})
        except (ValueError, TypeError, KeyError):
            _write({"id": request_id, "error": {
                "code": "DESKTOP_WORKER_ERROR",
                "message": "O worker rejeitou a operação.",
                "retryable": False,
            }})


if __name__ == "__main__":
    main()
