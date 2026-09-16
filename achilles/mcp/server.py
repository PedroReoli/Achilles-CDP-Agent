"""MCP stdio JSON-RPC para Python 3.9, sem dependência do SDK 3.10+."""

import asyncio
import json
import sys
from typing import Any, Dict, Optional, Union

from achilles.services.application import ApplicationServices
from achilles.services.errors import ServiceError

RequestId = Union[str, int]
VERSIONS = ("2025-06-18", "2024-11-05")


class MCPServer:
    def __init__(self, services: ApplicationServices) -> None:
        self.services = services
        self.initialized = False
        self.negotiated = False
        self.version = VERSIONS[0]

    @staticmethod
    def error(request_id: Any, code: int, message: str) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

    async def handle(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        request_id = request.get("id")
        method = request.get("method")
        if request.get("jsonrpc") != "2.0" or not isinstance(method, str):
            return self.error(request_id, -32600, "Invalid Request")
        params = request.get("params", {})
        if not isinstance(params, dict):
            return self.error(request_id, -32602, "Invalid params") if "id" in request else None
        if "id" not in request:
            if method == "notifications/initialized" and self.negotiated:
                self.initialized = True
            return None
        if not isinstance(request_id, (str, int)) or isinstance(request_id, bool):
            return self.error(None, -32600, "Invalid request id")
        result: Dict[str, Any]
        if method == "initialize":
            proposed = params.get("protocolVersion")
            self.version = proposed if proposed in VERSIONS else VERSIONS[0]
            self.negotiated = True
            result = {
                "protocolVersion": self.version,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "achilles-cdp", "version": "2.0.0"},
            }
        elif method == "ping":
            result = {}
        elif not self.initialized:
            return self.error(request_id, -32002, "Server not initialized")
        elif method == "tools/list":
            result = self.services.tools()
            if self.version == "2024-11-05":
                for tool in result["tools"]:
                    tool.pop("outputSchema", None)
                    tool.pop("annotations", None)
        elif method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments", {})
            if not isinstance(name, str) or not isinstance(arguments, dict):
                return self.error(request_id, -32602, "Invalid tool arguments")
            try:
                data = await self.services.call(name, arguments)
                result = {
                    "content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
                    "isError": False,
                }
                if self.version != "2024-11-05":
                    result["structuredContent"] = data
            except ServiceError as exc:
                result = {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps({"error": exc.as_dict()}, ensure_ascii=False),
                        }
                    ],
                    "isError": True,
                }
        else:
            return self.error(request_id, -32601, "Method not found")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}


async def run_mcp_stdio(cdp_port: int = 9222) -> None:
    services = ApplicationServices(cdp_port)
    server = MCPServer(services)
    pending: Dict[RequestId, asyncio.Task[Any]] = {}
    output_lock = asyncio.Lock()

    async def write(response: Dict[str, Any]) -> None:
        encoded = (json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8")
        # Backpressure / Context Protection
        if len(encoded) > 1048576:
            error_resp = server.error(response.get("id"), -32600, "Message too large for context window")
            encoded = (json.dumps(error_resp, ensure_ascii=False) + "\n").encode("utf-8")

        async with output_lock:
            await asyncio.to_thread(sys.stdout.buffer.write, encoded)
            await asyncio.to_thread(sys.stdout.buffer.flush)

    async def dispatch(request: Dict[str, Any]) -> None:
        request_id = request.get("id")
        try:
            response = await server.handle(request)
            if response is not None:
                await write(response)
        except asyncio.CancelledError:
            if "id" in request:
                await write(
                    server.error(
                        request_id, -32800, "Request cancelled; observe state before retrying"
                    )
                )
        except Exception:
            if "id" in request:
                await write(server.error(request_id, -32603, "Internal error"))
        finally:
            if isinstance(request_id, (str, int)):
                pending.pop(request_id, None)

    try:
        while True:
            line = await asyncio.to_thread(sys.stdin.buffer.readline, 1048577)
            if not line:
                break
            if len(line) > 1048576:
                await write(server.error(None, -32600, "Message too large"))
                break
            try:
                request = json.loads(line)
            except (ValueError, UnicodeError):
                await write(server.error(None, -32700, "Parse error"))
                continue
            if not isinstance(request, dict):
                await write(server.error(None, -32600, "Invalid Request"))
                continue
            if request.get("method") == "notifications/cancelled":
                params = request.get("params", {})
                target = params.get("requestId") if isinstance(params, dict) else None
                if isinstance(target, (str, int)) and target in pending:
                    pending[target].cancel()
                continue
            request_id = request.get("id")
            if (
                request.get("method") in ("initialize", "notifications/initialized")
                or "id" not in request
            ):
                await dispatch(request)
            elif not isinstance(request_id, (str, int)) or isinstance(request_id, bool):
                await write(server.error(None, -32600, "Invalid request id"))
            elif request_id in pending or len(pending) >= 32:
                await write(server.error(request_id, -32000, "Duplicate id or concurrency limit"))
            else:
                pending[request_id] = asyncio.create_task(dispatch(request))
        if pending:
            _, unfinished = await asyncio.wait(list(pending.values()), timeout=10)
            for task in unfinished:
                task.cancel()
            if unfinished:
                await asyncio.gather(*unfinished, return_exceptions=True)
    finally:
        for task in list(pending.values()):
            task.cancel()
        if pending:
            await asyncio.gather(*list(pending.values()), return_exceptions=True)
        await services.close()
