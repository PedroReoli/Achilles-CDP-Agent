"""
network_recorder.py — Buffer de requisições de rede, gerador de cURLs e exportador Postman v2.1.0.
"""
from typing import Any, Dict, List
from urllib.parse import urlparse


class NetworkRecorder:
    """Grava tráfego de rede e converte em cURLs reproduzíveis e coleções Postman."""

    def __init__(self, max_records: int = 500):
        self.max_records = max_records
        self.requests: List[Dict[str, Any]] = []

    def record(self, req_data: Dict[str, Any]):
        resource_type = req_data.get("resource_type", "")
        if resource_type in ["xhr", "fetch", "document"] or not resource_type:
            curl_cmd = self.to_curl(req_data)
            req_data["curl"] = curl_cmd
            self.requests.append(req_data)
            if len(self.requests) > self.max_records:
                self.requests.pop(0)

    @staticmethod
    def to_curl(req_data: Dict[str, Any]) -> str:
        url = req_data.get("url", "")
        method = req_data.get("method", "GET").upper()
        headers = req_data.get("headers", {})
        post_data = req_data.get("post_data")

        parts = [f"curl -X {method} '{url}'"]
        for k, v in headers.items():
            if not k.startswith(":"):
                clean_v = str(v).replace("'", "\'")
                parts.append(f"-H '{k}: {clean_v}'")

        if post_data and method in ["POST", "PUT", "PATCH", "DELETE"]:
            clean_data = str(post_data).replace("'", "\'")
            parts.append(f"--data-raw '{clean_data}'")

        return " \
  ".join(parts)

    def to_postman_collection(self, name: str = "Achilles Intercepted APIs") -> Dict[str, Any]:
        items = []
        for r in self.requests:
            url = r.get("url", "")
            method = r.get("method", "GET").upper()
            headers = r.get("headers", {})
            post_data = r.get("post_data")

            parsed = urlparse(url)
            header_list = [{"key": k, "value": str(v), "type": "text"} for k, v in headers.items() if not k.startswith(":")]
            
            req_item = {
                "name": f"{method} {parsed.path or '/'}",
                "request": {
                    "method": method,
                    "header": header_list,
                    "url": {
                        "raw": url,
                        "protocol": parsed.scheme,
                        "host": parsed.netloc.split("."),
                        "path": [p for p in parsed.path.split("/") if p]
                    }
                }
            }

            if post_data and method in ["POST", "PUT", "PATCH"]:
                req_item["request"]["body"] = {
                    "mode": "raw",
                    "raw": post_data,
                    "options": {"raw": {"language": "json"}}
                }

            items.append(req_item)

        return {
            "info": {
                "name": name,
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
            },
            "item": items
        }
