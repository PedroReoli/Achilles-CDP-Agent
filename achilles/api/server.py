"""REST local autenticado; toda operação delega aos Application Services."""

import hmac
import ipaddress
import os
import secrets
import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from achilles.services.application import ApplicationServices
from achilles.services.errors import ServiceError


class BodyLimit:
    def __init__(self, app: ASGIApp, max_bytes: int = 1048576) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        parts = []
        total = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body = message.get("body", b"")
            total += len(body)
            if total > self.max_bytes:
                await JSONResponse({"error": {"code": "PAYLOAD_TOO_LARGE"}}, status_code=413)(
                    scope, receive, send
                )
                return
            parts.append(body)
            if not message.get("more_body", False):
                break
        delivered = False

        async def bounded_receive() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": b"".join(parts), "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, send)


def create_app(
    cdp_port: int = 9222,
    token: Optional[str] = None,
    services: Optional[ApplicationServices] = None,
) -> FastAPI:
    configured_token = token or os.environ.get("ACHILLES_API_TOKEN")
    access_token = configured_token or secrets.token_urlsafe(32)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.services = services if services is not None else ApplicationServices(cdp_port)
        if not configured_token:
            print(f"Achilles local API token: {access_token}", file=sys.stderr)
        try:
            yield
        finally:
            await app.state.services.close()

    app = FastAPI(
        title="Achilles CDP Agent",
        version="2.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )
    app.add_middleware(BodyLimit)

    @app.middleware("http")
    async def local_only(request: Request, call_next: Any) -> Any:
        try:
            peer = ipaddress.ip_address(request.client.host if request.client else "0.0.0.0")
            raw_host = request.headers.get("host", "")
            if raw_host.startswith("["):
                host = raw_host.split("]", 1)[0].lstrip("[")
            else:
                host = raw_host.split(":", 1)[0]
            permitted = peer.is_loopback and host in ("127.0.0.1", "localhost", "::1")
        except ValueError:
            permitted = False
        if not permitted:
            return JSONResponse({"error": {"code": "LOOPBACK_REQUIRED"}}, status_code=403)
        if request.headers.get("origin"):
            return JSONResponse({"error": {"code": "BROWSER_ORIGIN_BLOCKED"}}, status_code=403)
        supplied = request.headers.get("authorization", "")
        if not hmac.compare_digest(
            supplied.encode("utf-8"), ("Bearer " + access_token).encode("utf-8")
        ):
            return JSONResponse({"error": {"code": "UNAUTHORIZED"}}, status_code=401)
        return await call_next(request)

    @app.exception_handler(ServiceError)
    async def service_error(request: Request, exc: ServiceError) -> JSONResponse:
        status = {
            "INVALID_ARGUMENT": 422,
            "UNKNOWN_TOOL": 404,
            "RECORD_NOT_FOUND": 404,
            "CDP_UNAVAILABLE": 503,
            "PAGE_CLOSED": 409,
            "STALE_ELEMENT_REF": 409,
        }.get(exc.code, 409)
        return JSONResponse({"error": exc.as_dict()}, status_code=status)

    @app.get("/api/tools.json")
    async def tools() -> Dict[str, Any]:
        return ApplicationServices.tools()

    @app.post("/api/tools/{name}")
    async def call(name: str, arguments: Dict[str, Any], request: Request) -> Dict[str, Any]:
        return await request.app.state.services.call(name, arguments)

    @app.get("/api/status")
    async def status(request: Request) -> Dict[str, Any]:
        return await request.app.state.services.call("browser_status", {})

    @app.get("/api/pages")
    async def pages(request: Request) -> Dict[str, Any]:
        return await request.app.state.services.call("browser_list_pages", {})

    @app.post("/api/pages/new")
    async def new_page(request: Request, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return await request.app.state.services.call("browser_new_tab", body or {})

    @app.delete("/api/pages/{page_id}")
    async def close_page(page_id: str, request: Request) -> Dict[str, Any]:
        return await request.app.state.services.call("browser_close_tab", {"page_id": page_id})

    @app.get("/api/dom/tree")
    async def tree(
        request: Request,
        page_id: Optional[str] = None,
        limit: int = 200,
        format: str = "compact",
        in_viewport_only: bool = True,
        selector: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await request.app.state.services.call(
            "browser_snapshot",
            {
                "page_id": page_id,
                "limit": limit,
                "format": format,
                "in_viewport_only": in_viewport_only,
                "selector": selector,
            },
        )

    @app.get("/api/read")
    async def read(
        request: Request, page_id: Optional[str] = None, max_length: int = 50000
    ) -> Dict[str, Any]:
        return await request.app.state.services.call(
            "browser_read_content", {"page_id": page_id, "max_length": max_length}
        )

    @app.get("/api/report")
    async def report(request: Request, page_id: Optional[str] = None) -> Dict[str, Any]:
        return await request.app.state.services.call("browser_report", {"page_id": page_id})

    @app.get("/api/security/audit")
    async def audit(request: Request, page_id: Optional[str] = None) -> Dict[str, Any]:
        return await request.app.state.services.call("security_audit", {"page_id": page_id})

    @app.get("/api/routes/apis")
    async def network(
        request: Request, page_id: Optional[str] = None, limit: int = 50
    ) -> Dict[str, Any]:
        return await request.app.state.services.call(
            "network_query", {"page_id": page_id, "limit": limit}
        )

    @app.get("/api/routes/postman")
    async def postman(request: Request) -> Dict[str, Any]:
        return await request.app.state.services.call("network_postman", {})

    @app.post("/api/action/{action}")
    async def action(request: Request, action: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return await request.app.state.services.call(
            "browser_action", {**arguments, "action": action}
        )

    @app.post("/api/challenge/wait")
    async def wait_challenge(
        request: Request, body: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        return await request.app.state.services.call("browser_wait_for_challenge", body or {})

    @app.get("/api/memory")
    async def get_memory(request: Request, domain: Optional[str] = None) -> Dict[str, Any]:
        return await request.app.state.services.call(
            "browser_domain_memory",
            {"operation": "get", "domain": domain} if domain else {"operation": "list"},
        )

    @app.post("/api/memory")
    async def remember_memory(request: Request, body: Dict[str, Any]) -> Dict[str, Any]:
        return await request.app.state.services.call(
            "browser_domain_memory",
            {"operation": "remember", **body},
        )

    @app.get("/api/report/html")
    async def report_html(request: Request, page_id: Optional[str] = None) -> Any:
        from fastapi.responses import HTMLResponse

        res = await request.app.state.services.call(
            "browser_export_html_report", {"page_id": page_id}
        )
        return HTMLResponse(content=res["html"])

    return app
