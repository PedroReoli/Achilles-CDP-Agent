"""MCP stdio JSON-RPC para Python 3.9, sem dependência do SDK 3.10+."""

import asyncio
import copy
import json
import sys
from typing import Any, Dict, Optional, Union

from achilles.services.application import ApplicationServices
from achilles.services.errors import ServiceError

RequestId = Union[str, int]
MODERN_VERSION = "2026-07-28"
LEGACY_VERSIONS = ("2025-11-25", "2025-06-18", "2024-11-05")
VERSIONS = (MODERN_VERSION,) + LEGACY_VERSIONS
SERVER_INFO = {"name": "achilles-cdp", "version": "2.1.0"}
VERSION_META = "io.modelcontextprotocol/protocolVersion"
CAPABILITIES_META = "io.modelcontextprotocol/clientCapabilities"
SERVER_INFO_META = "io.modelcontextprotocol/serverInfo"
MAX_MESSAGE_BYTES = 1048576


def encode_response(response: Dict[str, Any]) -> bytes:
    """Limita a saída por estrutura, preservando JSON válido e conteúdo consistente."""
    def encode(value: Dict[str, Any]) -> bytes:
        return (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")

    encoded = encode(response)
    if len(encoded) <= MAX_MESSAGE_BYTES:
        return encoded
    result = response.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("content"), list):
        return encode(MCPServer.error(response.get("id"), -32600, "Message too large for context window"))
    candidate = copy.deepcopy(response)
    result = candidate["result"]
    payload = result.get("structuredContent")
    if payload is None:
        try:
            payload = json.loads(result["content"][0]["text"])
        except (KeyError, IndexError, TypeError, ValueError):
            payload = None
    if payload is None:
        return encode(MCPServer.error(response.get("id"), -32600, "Message too large for context window"))

    def compact(value: Any, budget: int) -> Any:
        if isinstance(value, str):
            return value if len(value) <= budget else value[:budget] + "… [truncated]"
        if isinstance(value, list):
            return [compact(item, budget) for item in value[:max(1, budget // 256)]]
        if isinstance(value, dict):
            return {key: compact(item, budget) for key, item in value.items()}
        return value

    for budget in (65536, 16384, 4096, 1024, 256):
        shortened = compact(payload, budget)
        if isinstance(shortened, dict):
            shortened["truncated_by_context_limit"] = True
        result["content"] = [{"type": "text", "text": json.dumps(shortened, ensure_ascii=False)}]
        if "structuredContent" in result:
            result["structuredContent"] = shortened
        encoded = encode(candidate)
        if len(encoded) <= MAX_MESSAGE_BYTES:
            return encoded
    return encode(MCPServer.error(response.get("id"), -32600, "Message too large for context window"))


class MCPServer:
    def __init__(self, services: ApplicationServices) -> None:
        self.services = services
        self.initialized = False
        self.negotiated = False
        self.version = LEGACY_VERSIONS[0]
        self.era: Optional[str] = None

    @staticmethod
    def error(request_id: Any, code: int, message: str) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

    @staticmethod
    def unsupported_version(request_id: Any, requested: Any) -> Dict[str, Any]:
        response = MCPServer.error(request_id, -32022, "Unsupported protocol version")
        response["error"]["data"] = {"supported": list(VERSIONS), "requested": requested}
        return response

    async def handle(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        request_id = request.get("id")
        method = request.get("method")
        if request.get("jsonrpc") != "2.0" or not isinstance(method, str):
            return self.error(request_id, -32600, "Invalid Request")
        params = request.get("params", {})
        if not isinstance(params, dict):
            return self.error(request_id, -32602, "Invalid params") if "id" in request else None
        if "id" not in request:
            if method == "notifications/initialized" and self.era == "legacy":
                self.initialized = True
            return None
        if not isinstance(request_id, (str, int)) or isinstance(request_id, bool):
            return self.error(None, -32600, "Invalid request id")
        result: Dict[str, Any]
        modern = False
        if method == "initialize":
            if self.era == "modern":
                return self.error(request_id, -32600, "Protocol era already selected")
            proposed = params.get("protocolVersion")
            self.version = proposed if proposed in LEGACY_VERSIONS else LEGACY_VERSIONS[0]
            self.negotiated = True
            self.era = "legacy"
            result = {
                "protocolVersion": self.version,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            }
        elif method == "ping" and self.era != "modern":
            result = {}
        else:
            metadata = params.get("_meta")
            modern_request = method == "server/discover" or (
                isinstance(metadata, dict) and VERSION_META in metadata
            )
            if modern_request:
                if self.era == "legacy":
                    return self.error(request_id, -32600, "Protocol era already selected")
                if not isinstance(metadata, dict) or not isinstance(
                    metadata.get(CAPABILITIES_META), dict
                ):
                    return self.error(request_id, -32602, "Missing modern protocol metadata")
                requested = metadata.get(VERSION_META)
                if requested != MODERN_VERSION:
                    return self.unsupported_version(request_id, requested)
                self.era = "modern"
                modern = True
            elif self.era == "modern":
                return self.error(request_id, -32602, "Missing modern protocol metadata")
            elif not self.negotiated:
                return self.error(request_id, -32002, "Server not initialized")

            if method == "server/discover":
                result = {
                    "supportedVersions": list(VERSIONS),
                    "capabilities": {"tools": {}},
                }
            elif method == "tools/list":
                result = self.services.tools()
                if not modern and self.version == "2024-11-05":
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
                    text_payload = data
                    if (modern or self.version != "2024-11-05") and name == "browser_snapshot":
                        text_payload = {
                            key: data[key]
                            for key in ("snapshot_id", "page_id", "compact", "warnings", "tokens_saved_percent")
                            if key in data
                        }
                    elif (modern or self.version != "2024-11-05") and name == "browser_read_content":
                        text_payload = {
                            key: data[key]
                            for key in ("page_id", "url", "title", "markdown", "tokens_saved_percent")
                            if key in data
                        }
                    result = {
                        "content": [{"type": "text", "text": json.dumps(text_payload, ensure_ascii=False)}],
                        "isError": False,
                    }
                    if modern or self.version != "2024-11-05":
                        result["structuredContent"] = data
                except ServiceError as exc:
                    result = {
                        "content": [
                            {"type": "text", "text": json.dumps({"error": exc.as_dict()}, ensure_ascii=False)}
                        ],
                        "isError": True,
                    }
            else:
                return self.error(request_id, -32601, "Method not found")
            if modern:
                result["resultType"] = "complete"
                result["_meta"] = {SERVER_INFO_META: SERVER_INFO}
                if method in ("server/discover", "tools/list"):
                    result["ttlMs"] = 300000
                    result["cacheScope"] = "public"
        return {"jsonrpc": "2.0", "id": request_id, "result": result}


async def run_mcp_stdio(cdp_port: int = 9222) -> None:
    services = ApplicationServices(cdp_port)
    server = MCPServer(services)
    pending: Dict[RequestId, asyncio.Task[Any]] = {}
    output_lock = asyncio.Lock()

    async def write(response: Dict[str, Any]) -> None:
        encoded = encode_response(response)

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
        except Exception as exc:
            import traceback
            traceback.print_exc(file=sys.stderr)
            if "id" in request:
                await write(server.error(request_id, -32603, f"Internal error: {type(exc).__name__}"))
        finally:
            if isinstance(request_id, (str, int)):
                pending.pop(request_id, None)

    try:
        while True:
            line = await asyncio.to_thread(sys.stdin.buffer.readline, MAX_MESSAGE_BYTES + 1)
            if not line:
                break
            if len(line) > MAX_MESSAGE_BYTES:
                while not line.endswith(b"\n"):
                    line = await asyncio.to_thread(sys.stdin.buffer.readline, MAX_MESSAGE_BYTES + 1)
                    if not line:
                        break
                await write(server.error(None, -32600, "Message too large"))
                continue
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
                request.get("method") in ("initialize", "server/discover", "notifications/initialized")
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
