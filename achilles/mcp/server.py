"""
server.py — Servidor MCP (Model Context Protocol) nativo para integração com Claude Desktop, Cursor e Antigravity.
"""
import sys
import json
import asyncio
from typing import Dict, Any

from achilles.core.cdp_driver import CDPDriver
from achilles.core.dom_parser import DOMSemanticParser
from achilles.security.auditor import SecurityAuditor
from achilles.reverse_api.openapi import OpenAPIGenerator

driver = CDPDriver()


async def handle_mcp_request(req: Dict[str, Any]) -> Dict[str, Any]:
    method = req.get("method")
    req_id = req.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "achilles-cdp-mcp", "version": "1.0.0"}
            }
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {
                        "name": "achilles_get_dom_tree",
                        "description": "Retorna árvore semântica compacta com IDs numéricos para a IA entender e agir na página.",
                        "inputSchema": {"type": "object", "properties": {}}
                    },
                    {
                        "name": "achilles_click_id",
                        "description": "Executa clique no elemento pelo ID numérico retornado por achilles_get_dom_tree.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"id": {"type": "integer", "description": "ID numérico do elemento"}},
                            "required": ["id"]
                        }
                    },
                    {
                        "name": "achilles_fill_id",
                        "description": "Preenche um input pelo ID numérico.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "integer", "description": "ID numérico do campo"},
                                "value": {"type": "string", "description": "Texto a preencher"}
                            },
                            "required": ["id", "value"]
                        }
                    },
                    {
                        "name": "achilles_security_audit",
                        "description": "Executa auditoria de vulnerabilidades OWASP Top 10, Supabase RLS e vazamento de secrets na aba ativa.",
                        "inputSchema": {"type": "object", "properties": {}}
                    }
                ]
            }
        }

    if method == "tools/call":
        params = req.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {})

        page = await driver.get_page()

        if tool_name == "achilles_get_dom_tree":
            data = await page.evaluate(DOMSemanticParser.JS_EXTRACT_TREE)
            tree_text = DOMSemanticParser.format_tree_for_llm(data["elements"])
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": tree_text}]}
            }

        elif tool_name == "achilles_click_id":
            target_id = args.get("id")
            data = await page.evaluate(DOMSemanticParser.JS_EXTRACT_TREE)
            target = next((el for el in data["elements"] if el["id"] == target_id), None)
            if not target:
                return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32602, "message": f"Elemento #{target_id} não encontrado"}}
            b = target["bounds"]
            await page.mouse.click(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": f"Clicado em elemento #{target_id}: {target.get('text')}"}]}}

        elif tool_name == "achilles_fill_id":
            target_id = args.get("id")
            val = args.get("value", "")
            data = await page.evaluate(DOMSemanticParser.JS_EXTRACT_TREE)
            target = next((el for el in data["forms"] if el["id"] == target_id), None)
            if not target:
                return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32602, "message": f"Campo #{target_id} não encontrado"}}
            b = target["bounds"]
            await page.mouse.click(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
            await page.keyboard.type(val, delay=15)
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": f"Preenchido campo #{target_id} com sucesso"}]}}

        elif tool_name == "achilles_security_audit":
            storage = await page.evaluate("() => ({ localStorage: { ...localStorage }, sessionStorage: { ...sessionStorage } })")
            cookies = await page.context.cookies([page.url])
            dom_meta = await page.evaluate(DOMSemanticParser.JS_EXTRACT_TREE)
            audit_res = SecurityAuditor.audit(page.url, await page.title(), {}, cookies, storage["localStorage"], storage["sessionStorage"], [], dom_meta)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(audit_res, indent=2, ensure_ascii=False)}]}
            }

    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Método não encontrado: {method}"}}


async def run_mcp_stdio():
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    while True:
        line = await reader.readline()
        if not line:
            break
        try:
            req = json.loads(line.decode("utf-8"))
            res = await handle_mcp_request(req)
            sys.stdout.write(json.dumps(res) + "\n")
            sys.stdout.flush()
        except Exception as e:
            err_res = {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(e)}}
            sys.stdout.write(json.dumps(err_res) + "\n")
            sys.stdout.flush()
