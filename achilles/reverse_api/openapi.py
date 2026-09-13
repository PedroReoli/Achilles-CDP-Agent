"""
openapi.py — Gerador Reverso de OpenAPI 3.0.0 e Swagger UI Dinâmico.
"""
import re
import json
from typing import Dict, Any, List
from urllib.parse import urlparse, parse_qs


class OpenAPIGenerator:
    """Analisa tráfego HTTP capturado e sintetiza especificações OpenAPI 3.0.0."""

    @staticmethod
    def infer_schema(data: Any) -> Dict[str, Any]:
        if data is None:
            return {"type": "string", "nullable": True}
        if isinstance(data, bool):
            return {"type": "boolean"}
        if isinstance(data, int):
            return {"type": "integer"}
        if isinstance(data, float):
            return {"type": "number"}
        if isinstance(data, str):
            return {"type": "string"}
        if isinstance(data, list):
            item_schema = OpenAPIGenerator.infer_schema(data[0]) if data else {"type": "string"}
            return {"type": "array", "items": item_schema}
        if isinstance(data, dict):
            properties = {k: OpenAPIGenerator.infer_schema(v) for k, v in data.items()}
            return {"type": "object", "properties": properties}
        return {"type": "string"}

    @classmethod
    def generate_spec(cls, requests: List[Dict[str, Any]], title: str = "Achilles Reverse-Engineered API") -> Dict[str, Any]:
        paths = {}
        for req in requests:
            url = req.get("url", "")
            method = req.get("method", "GET").lower()
            post_data = req.get("post_data")

            parsed = urlparse(url)
            path_template = parsed.path or "/"
            path_clean = re.sub(r'/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '/{id}', path_template, flags=re.IGNORECASE)
            path_clean = re.sub(r'/[0-9]{2,10}', '/{id}', path_clean)

            if path_clean not in paths:
                paths[path_clean] = {}

            operation = {
                "summary": f"{method.upper()} {path_clean}",
                "description": f"Capturado automaticamente pelo Achilles CDP Agent via {parsed.netloc}",
                "parameters": [],
                "responses": {"200": {"description": "OK (Captured Payload)"}}
            }

            for p_name, p_vals in parse_qs(parsed.query).items():
                operation["parameters"].append({
                    "name": p_name,
                    "in": "query",
                    "required": False,
                    "schema": {"type": "string", "example": p_vals[0] if p_vals else ""}
                })

            if "{id}" in path_clean:
                operation["parameters"].append({
                    "name": "id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string"}
                })

            if post_data and method in ["post", "put", "patch"]:
                try:
                    body_json = json.loads(post_data)
                    operation["requestBody"] = {
                        "required": True,
                        "content": {"application/json": {"schema": cls.infer_schema(body_json), "example": body_json}}
                    }
                except Exception:
                    operation["requestBody"] = {
                        "content": {"text/plain": {"schema": {"type": "string"}}}
                    }

            paths[path_clean][method] = operation

        return {
            "openapi": "3.0.0",
            "info": {"title": title, "version": "1.0.0", "description": "Especificação gerada pelo Achilles CDP Agent."},
            "paths": paths
        }

    @staticmethod
    def get_swagger_html(openapi_json_url: str = "/api/routes/openapi.json") -> str:
        return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Achilles CDP — Live Swagger UI</title>
    <link rel="stylesheet" type="text/css" href="https://unpkg.com/swagger-ui-dist@5.11.0/swagger-ui.css">
    <style>body {{ margin: 0; background: #0f172a; }} .swagger-ui {{ filter: invert(88%) hue-rotate(180deg); }} .swagger-ui .topbar {{ display: none; }}</style>
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist@5.11.0/swagger-ui-bundle.js"></script>
    <script>
        window.onload = () => {{
            SwaggerUIBundle({{ url: '{openapi_json_url}', dom_id: '#swagger-ui', presets: [SwaggerUIBundle.presets.apis], layout: "BaseLayout" }});
        }};
    </script>
</body>
</html>"""
