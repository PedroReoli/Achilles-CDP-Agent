"""Interface web local para acompanhar e operar o runtime Achilles QA."""

import hmac
import ipaddress
import secrets
from contextlib import asynccontextmanager
from importlib.resources import files
from typing import Any, AsyncIterator, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from achilles import __version__
from achilles.services.application import ApplicationServices
from achilles.services.errors import ServiceError

QA_STUDIO_TOOLS = {
    "qa_status",
    "qa_discover",
    "qa_plan",
    "qa_request",
    "qa_run_suite",
    "qa_report",
    "qa_security_audit",
    "qa_runs",
}


def create_studio_app(
    cdp_port: int = 9222,
    services: Optional[ApplicationServices] = None,
    studio_token: Optional[str] = None,
) -> FastAPI:
    token = studio_token or secrets.token_urlsafe(32)
    static = files("achilles.studio").joinpath("static")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.services = services if services is not None else ApplicationServices(cdp_port)
        try:
            yield
        finally:
            await app.state.services.close()

    app = FastAPI(
        title="Achilles QA Studio",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def studio_security(request: Request, call_next: Any) -> Any:
        try:
            peer = ipaddress.ip_address(request.client.host if request.client else "0.0.0.0")
            raw_host = request.headers.get("host", "")
            host = raw_host.split(":", 1)[0].strip("[]")
            permitted = peer.is_loopback and host in ("127.0.0.1", "localhost", "::1")
        except ValueError:
            permitted = False
        if not permitted:
            return JSONResponse({"error": {"code": "LOOPBACK_REQUIRED"}}, status_code=403)
        if request.url.path.startswith("/api/"):
            supplied = request.headers.get("x-achilles-studio-token", "")
            if not hmac.compare_digest(supplied.encode(), token.encode()):
                return JSONResponse({"error": {"code": "UNAUTHORIZED"}}, status_code=401)
            origin = request.headers.get("origin")
            if origin and origin not in (
                f"http://{raw_host}",
                f"https://{raw_host}",
            ):
                return JSONResponse({"error": {"code": "ORIGIN_DENIED"}}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
        )
        return response

    @app.exception_handler(ServiceError)
    async def service_error(request: Request, exc: ServiceError) -> JSONResponse:
        status = 422 if exc.code.startswith(("INVALID", "QA_")) else 409
        return JSONResponse({"error": exc.as_dict()}, status_code=status)

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        source = static.joinpath("index.html").read_text(encoding="utf-8")
        return HTMLResponse(source.replace("__ACHILLES_STUDIO_TOKEN__", token))

    @app.get("/assets/{name}")
    async def asset(name: str) -> FileResponse:
        if name not in ("styles.css", "app.js"):
            return JSONResponse({"error": {"code": "NOT_FOUND"}}, status_code=404)
        return FileResponse(str(static.joinpath(name)))

    @app.get("/api/catalog")
    async def catalog() -> Dict[str, Any]:
        return ApplicationServices.tools(QA_STUDIO_TOOLS)

    @app.get("/api/status")
    async def status(request: Request) -> Dict[str, Any]:
        return await request.app.state.services.call("qa_status", {})

    @app.get("/api/runs")
    async def runs(request: Request, limit: int = 20) -> Dict[str, Any]:
        return await request.app.state.services.call("qa_runs", {"limit": min(max(limit, 1), 100)})

    @app.get("/api/runs/{run_id}")
    async def report(run_id: str, request: Request) -> Dict[str, Any]:
        return await request.app.state.services.call(
            "qa_report", {"run_id": run_id, "format": "json"}
        )

    @app.post("/api/tools/{name}")
    async def tool(name: str, arguments: Dict[str, Any], request: Request) -> Dict[str, Any]:
        if name not in QA_STUDIO_TOOLS:
            return JSONResponse({"error": {"code": "TOOL_DENIED"}}, status_code=404)
        return await request.app.state.services.call(name, arguments)

    return app
