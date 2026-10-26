"""Fachada assíncrona para o backend Windows UI Automation."""

import asyncio
import json
import os
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any, Dict, Optional

from .desktop_protocol import DESKTOP_METHODS, MAX_WORKER_MESSAGE
from .errors import ServiceError
from .windows_desktop_backend import WindowsDesktopBackend


class DesktopService:
    """Serializa UIA em uma thread dedicada e mantém o event loop responsivo."""

    def __init__(self, policy: Any = None, backend: Optional[WindowsDesktopBackend] = None) -> None:
        self.backend = backend
        self.policy = policy
        self.executor = (
            ThreadPoolExecutor(max_workers=1, thread_name_prefix="achilles-uia")
            if backend is not None else None
        )
        self.process: Optional[asyncio.subprocess.Process] = None
        self.lock = asyncio.Lock()
        self.closed = False

    async def _run(self, method: str, **arguments: Any) -> Dict[str, Any]:
        if self.backend is None or self.executor is None:
            raise ServiceError("DESKTOP_WORKER_ERROR", "Backend local indisponível.")
        loop = asyncio.get_running_loop()
        function = partial(getattr(self.backend, method), **arguments)
        return await loop.run_in_executor(self.executor, function)

    async def _ensure_worker(self) -> asyncio.subprocess.Process:
        if self.process is not None and self.process.returncode is None:
            return self.process
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self.process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "achilles.services.desktop_worker",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            creationflags=flags,
            limit=MAX_WORKER_MESSAGE,
        )
        return self.process

    async def _worker_call(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        async with self.lock:
            process = await self._ensure_worker()
            request_id = uuid.uuid4().hex
            encoded = (json.dumps({
                "id": request_id, "name": name, "arguments": arguments,
            }, ensure_ascii=False) + "\n").encode("utf-8")
            if len(encoded) > MAX_WORKER_MESSAGE:
                raise ServiceError("DESKTOP_REQUEST_TOO_LARGE", "Operação excedeu 2 MiB.")
            if process.stdin is None or process.stdout is None:
                raise ServiceError("DESKTOP_WORKER_ERROR", "Pipes do worker indisponíveis.")
            process.stdin.write(encoded)
            await process.stdin.drain()
            raw = await asyncio.wait_for(process.stdout.readline(), timeout=85)
            if not raw:
                raise ServiceError(
                    "DESKTOP_WORKER_STOPPED",
                    "O worker de desktop encerrou inesperadamente; repita a operação.",
                    retryable=True,
                )
            response = json.loads(raw)
            if response.get("id") != request_id:
                raise ServiceError("DESKTOP_WORKER_ERROR", "Resposta fora de ordem do worker.")
            if response.get("error"):
                error = response["error"]
                raise ServiceError(
                    error.get("code", "DESKTOP_WORKER_ERROR"),
                    error.get("message", "Falha no worker de desktop."),
                    bool(error.get("retryable")),
                    error.get("recovery"),
                )
            return response["result"]

    async def call(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if self.backend is not None:
            return await self._run(DESKTOP_METHODS[name], **arguments)
        return await self._worker_call(name, arguments)

    async def close(self) -> None:
        if not self.closed:
            if self.process is not None and self.process.returncode is None:
                try:
                    await self._worker_call("shutdown", {})
                    await asyncio.wait_for(self.process.wait(), timeout=2)
                except (ServiceError, asyncio.TimeoutError, BrokenPipeError):
                    self.process.terminate()
            if self.executor is not None:
                self.executor.shutdown(wait=False, cancel_futures=True)
            self.closed = True
