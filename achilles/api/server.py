"""
server.py — Servidor FastAPI do Achilles CDP Agent.
"""
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel

from achilles.core.cdp_driver import CDPDriver
from achilles.core.dom_parser import DOMSemanticParser
from achilles.core.network_recorder import NetworkRecorder
from achilles.core.visual_overlay import JS_INJECT_OVERLAY, JS_REMOVE_OVERLAY
from achilles.security.auditor import SecurityAuditor
from achilles.reverse_api.openapi import OpenAPIGenerator
from achilles.testing.playwright_exporter import PlaywrightTestExporter

driver = CDPDriver()
recorder = NetworkRecorder()
driver.register_request_callback(recorder.record)

app = FastAPI(
    title="Achilles CDP Agent API",
    description="Interface REST e AI Bridge para Automação, Engenharia Reversa e Auditoria de Browser via CDP.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/status")
async def get_status():
    page = await driver.get_page()
    return {
        "status": "connected",
        "cdp_url": driver.cdp_url,
        "title": await page.title(),
        "url": page.url,
        "recorded_requests": len(recorder.requests)
    }


@app.get("/api/dom/tree")
async def get_dom_tree(format_for_llm: bool = Query(True)):
    page = await driver.get_page()
    data = await page.evaluate(DOMSemanticParser.JS_EXTRACT_TREE)
    if format_for_llm:
        return {
            "title": data["title"],
            "url": data["url"],
            "total_elements": len(data["elements"]),
            "llm_prompt_tree": DOMSemanticParser.format_tree_for_llm(data["elements"]),
            "elements": data["elements"]
        }
    return data


@app.post("/api/dom/highlight")
async def inject_highlight():
    page = await driver.get_page()
    res = await page.evaluate(JS_INJECT_OVERLAY)
    return {"success": True, "details": res}


@app.post("/api/dom/clear-highlight")
async def clear_highlight():
    page = await driver.get_page()
    res = await page.evaluate(JS_REMOVE_OVERLAY)
    return {"success": True, "details": res}


@app.get("/api/routes/apis")
async def get_apis(limit: int = 50):
    return {"total": len(recorder.requests), "requests": recorder.requests[:limit]}


@app.get("/api/routes/postman")
async def get_postman():
    return recorder.to_postman_collection("Achilles Exported APIs")


@app.get("/api/routes/openapi.json")
async def get_openapi_spec(title: str = "Achilles Reverse API"):
    return OpenAPIGenerator.generate_spec(recorder.requests, title=title)


@app.get("/api/routes/swagger", response_class=HTMLResponse)
async def get_swagger_ui():
    return OpenAPIGenerator.get_swagger_html("/api/routes/openapi.json")


@app.get("/api/export/playwright-test", response_class=PlainTextResponse)
async def export_playwright():
    page = await driver.get_page()
    return PlaywrightTestExporter.generate_python(page.url, recorder.requests)


@app.get("/api/security/audit")
async def run_audit():
    page = await driver.get_page()
    js_storage = """
    () => {
        const local = {};
        for (let i = 0; i < localStorage.length; i++) local[localStorage.key(i)] = localStorage.getItem(localStorage.key(i));
        const session = {};
        for (let i = 0; i < sessionStorage.length; i++) session[sessionStorage.key(i)] = sessionStorage.getItem(sessionStorage.key(i));
        return { localStorage: local, sessionStorage: session };
    }
    """
    storage = await page.evaluate(js_storage)
    cookies = await page.context.cookies([page.url])
    dom_meta = await page.evaluate(DOMSemanticParser.JS_EXTRACT_TREE)
    
    main_headers = {}
    for r in reversed(recorder.requests):
        if r.get("url") == page.url:
            main_headers = r.get("headers", {})
            break

    return SecurityAuditor.audit(
        page_url=page.url,
        page_title=await page.title(),
        page_headers=main_headers,
        cookies=cookies,
        local_storage=storage.get("localStorage", {}),
        session_storage=storage.get("sessionStorage", {}),
        recorded_requests=recorder.requests,
        dom_meta=dom_meta
    )


class ClickModel(BaseModel):
    id: Optional[int] = None
    selector: Optional[str] = None
    text: Optional[str] = None


class FillModel(BaseModel):
    id: Optional[int] = None
    selector: Optional[str] = None
    value: str


@app.post("/api/action/click")
async def click_action(req: ClickModel):
    page = await driver.get_page()
    if req.id:
        data = await page.evaluate(DOMSemanticParser.JS_EXTRACT_TREE)
        target = next((el for el in data["elements"] if el["id"] == req.id), None)
        if not target:
            raise HTTPException(404, f"Elemento #{req.id} não encontrado")
        b = target["bounds"]
        await page.mouse.click(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
        return {"success": True, "clicked": target}
    elif req.selector:
        await page.click(req.selector)
        return {"success": True, "selector": req.selector}
    elif req.text:
        await page.click(f"text={req.text}")
        return {"success": True, "text": req.text}
    raise HTTPException(400, "Forneça id, selector ou text")


@app.post("/api/action/fill")
async def fill_action(req: FillModel):
    page = await driver.get_page()
    if req.id:
        data = await page.evaluate(DOMSemanticParser.JS_EXTRACT_TREE)
        target = next((el for el in data["forms"] if el["id"] == req.id), None)
        if not target:
            raise HTTPException(404, f"Input #{req.id} não encontrado")
        b = target["bounds"]
        await page.mouse.click(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
        await page.keyboard.type(req.value, delay=15)
        return {"success": True, "filled": target, "value": req.value}
    elif req.selector:
        await page.fill(req.selector, req.value)
        return {"success": True, "selector": req.selector}
    raise HTTPException(400, "Forneça id ou selector")


@app.get("/api/tools.json")
async def get_tools():
    return {
        "tools": [
            {"name": "get_dom_tree", "description": "Obtém árvore semântica com IDs para decidir ação"},
            {"name": "click_element", "description": "Clica em elemento por ID numérico ou texto"},
            {"name": "fill_input", "description": "Digita em input por ID numérico"},
            {"name": "run_security_audit", "description": "Audita OWASP, RLS e headers da página"},
            {"name": "highlight_elements", "description": "Injeta badges [#1], [#2] visuais no Chrome"},
            {"name": "get_api_curls", "description": "Retorna requisições XHR/Fetch com cURLs prontos"}
        ]
    }
