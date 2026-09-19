"""Registro HTTP correlacionado e limitado; exports sempre redigidos."""

import asyncio
import copy
import shlex
import time
import uuid
from collections import deque
from typing import TYPE_CHECKING, Any, Deque, Dict, List, Optional
from urllib.parse import parse_qsl, urlsplit

from .redaction import redact, redact_body, redact_url

if TYPE_CHECKING:
    from playwright.async_api import Request, Response


class TrafficJournal:
    def __init__(self, max_records: int = 500, max_body_bytes: int = 65536) -> None:
        if max_records < 1 or max_body_bytes < 1:
            raise ValueError("Limites devem ser positivos")
        self.records: Deque[Dict[str, Any]] = deque(maxlen=max_records)
        self.max_body_bytes = max_body_bytes
        self._index: Dict["Request", Dict[str, Any]] = {}
        self._body_slots: Optional[asyncio.Semaphore] = None
        self.dropped_events = 0

    def request(self, request: "Request", page_id: Optional[str]) -> None:
        if len(self.records) == self.records.maxlen:
            old = self.records[0]
            self._index.pop(old["_key"], None)
        try:
            body = request.post_data or ""
        except Exception:
            body = ""
        encoded_body = body.encode("utf-8")
        redirected = request.redirected_from if hasattr(request, "redirected_from") else None
        predecessor = self._index.get(redirected) if redirected is not None else None
        record: Dict[str, Any] = {
            "_key": request,
            "request_id": uuid.uuid4().hex,
            "page_id": page_id,
            "method": request.method,
            "url": request.url,
            "resource_type": request.resource_type,
            "started_at": time.time(),
            "request_headers": dict(request.headers),
            "request_body": encoded_body[: self.max_body_bytes].decode("utf-8", errors="replace"),
            "request_body_truncated": len(encoded_body) > self.max_body_bytes,
            "redirected_from": predecessor["request_id"] if predecessor else None,
            "status": None,
            "response_headers": {},
            "response_body": None,
            "body_state": "pending",
            "timings": {},
            "failure": None,
        }
        self.records.append(record)
        self._index[request] = record

    async def response(self, response: "Response") -> None:
        record = self._index.get(response.request)
        if record is None:
            return
        record["status"] = response.status
        record["response_headers"] = dict(response.headers)
        try:
            record["response_headers"] = await response.all_headers()
            record["request_headers"] = await response.request.all_headers()
        except Exception:
            record["headers_incomplete"] = True

    async def finished(self, request: "Request") -> None:
        record = self._index.get(request)
        if record is None:
            return
        record["timings"] = dict(request.timing)
        try:
            if self._body_slots is None:
                self._body_slots = asyncio.Semaphore(4)
            async with self._body_slots:
                response = await request.response()
                if response is None:
                    record["body_state"] = "unavailable"
                    return
                await self.response(response)
                headers = record["response_headers"]
                mime = headers.get("content-type", "").lower()
                length = headers.get("content-length", "")
                if "text/event-stream" in mime:
                    record["body_state"] = "streaming_not_captured"
                    return
                if not any(t in mime for t in ("json", "text/", "javascript", "xml")):
                    record["body_state"] = "binary_omitted"
                    return
                if (
                    not length.isdigit()
                    or int(length) > self.max_body_bytes
                    or headers.get("content-encoding")
                ):
                    record["body_state"] = "size_or_encoding_omitted"
                    return
                body = await asyncio.wait_for(response.body(), timeout=5)
                record["response_body"] = body[: self.max_body_bytes].decode(
                    "utf-8", errors="replace"
                )
                record["body_state"] = (
                    "truncated" if len(body) > self.max_body_bytes else "captured"
                )
        except Exception:
            record["body_state"] = "unavailable"

    def failed(self, request: "Request") -> None:
        record = self._index.get(request)
        if record is not None:
            record["failure"] = "NETWORK_REQUEST_FAILED"
            record["timings"] = dict(request.timing)
            record["body_state"] = "failed"

    def query(self, limit: int = 50, page_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if not 1 <= limit <= 500:
            raise ValueError("limit deve estar entre 1 e 500")
        rows = [r for r in self.records if page_id is None or r["page_id"] == page_id]
        return [self.public_record(r) for r in rows[-limit:]]

    def clear(self) -> None:
        self.records.clear()
        self._index.clear()

    @staticmethod
    def public_record(record: Dict[str, Any]) -> Dict[str, Any]:
        result = copy.deepcopy({k: v for k, v in record.items() if not k.startswith("_")})
        result["url"] = redact_url(result["url"])
        for side in ("request", "response"):
            headers = result.get(side + "_headers", {})
            body = result.get(side + "_body")
            if body is not None:
                result[side + "_body"] = redact_body(body, headers.get("content-type", ""))
            result[side + "_headers"] = redact(headers)
        return result

    def navigation(self, page_id: str, url: str) -> Optional[Dict[str, Any]]:
        return next(
            (
                r
                for r in reversed(self.records)
                if r["page_id"] == page_id
                and r["resource_type"] == "document"
                and r["url"].split("#")[0] == url.split("#")[0]
                and r["status"] is not None
            ),
            None,
        )

    @staticmethod
    def to_curl(record: Dict[str, Any], shell: str = "posix") -> str:
        if shell not in ("posix", "powershell"):
            raise ValueError("Shell inválido")
        r = TrafficJournal.public_record(record)
        args = [
            "curl" if shell == "posix" else "curl.exe",
            "--request",
            r["method"],
            "--url",
            r["url"],
        ]
        for key, value in r["request_headers"].items():
            if not key.startswith(":") and key.lower() not in ("content-length", "host"):
                args.extend(["--header", f"{key}: {value}"])
        if r.get("request_body"):
            args.extend(["--data-raw", r["request_body"]])
        if shell == "posix":
            return " ".join(shlex.quote(a) for a in args)
        return "& " + " ".join("'" + a.replace("'", "''") + "'" for a in args)

    def postman(self) -> Dict[str, Any]:
        items: List[Dict[str, Any]] = []
        for raw in self.records:
            r = self.public_record(raw)
            p = urlsplit(r["url"])
            url: Dict[str, Any] = {
                "raw": r["url"],
                "protocol": p.scheme,
                "host": (p.hostname or "").split("."),
                "path": p.path.strip("/").split("/") if p.path.strip("/") else [],
                "query": [
                    {"key": k, "value": v} for k, v in parse_qsl(p.query, keep_blank_values=True)
                ],
            }
            if p.port:
                url["port"] = str(p.port)
            request: Dict[str, Any] = {
                "method": r["method"],
                "url": url,
                "header": [
                    {"key": k, "value": str(v)}
                    for k, v in r["request_headers"].items()
                    if not k.startswith(":")
                ],
            }
            if r.get("request_body"):
                request["body"] = {"mode": "raw", "raw": r["request_body"]}
            items.append({"name": f"{r['method']} {p.path}", "request": request})
        return {
            "info": {
                "name": "Achilles — redacted",
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            },
            "item": items,
        }

    def get_routes_report(self, page_id: Optional[str] = None) -> Dict[str, Any]:
        records = [r for r in self.records if page_id is None or r.get("page_id") == page_id]
        domains: Dict[str, int] = {}
        methods: Dict[str, int] = {}
        statuses: Dict[str, int] = {"2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0, "failed": 0, "other": 0}
        api_endpoints: List[Dict[str, Any]] = []
        seen_apis = set()

        for raw in records:
            r = self.public_record(raw)
            method = r.get("method", "GET")
            methods[method] = methods.get(method, 0) + 1

            url = r.get("url", "")
            parsed = urlsplit(url)
            host = parsed.hostname or "unknown"
            domains[host] = domains.get(host, 0) + 1

            status = r.get("status")
            if r.get("failure"):
                statuses["failed"] += 1
            elif status is None:
                statuses["other"] += 1
            elif 200 <= status < 300:
                statuses["2xx"] += 1
            elif 300 <= status < 400:
                statuses["3xx"] += 1
            elif 400 <= status < 500:
                statuses["4xx"] += 1
            elif 500 <= status < 600:
                statuses["5xx"] += 1
            else:
                statuses["other"] += 1

            res_type = r.get("resource_type", "")
            req_headers = r.get("request_headers", {})
            resp_headers = r.get("response_headers", {})
            is_api = (
                res_type in ("xhr", "fetch")
                or "application/json" in req_headers.get("accept", "")
                or "application/json" in resp_headers.get("content-type", "")
                or "/api/" in parsed.path
                or "/graphql" in parsed.path
                or "/v1/" in parsed.path
                or "/v2/" in parsed.path
            )
            api_key = f"{method} {parsed.scheme}://{host}{parsed.path}"
            if is_api and api_key not in seen_apis:
                seen_apis.add(api_key)
                api_endpoints.append({
                    "method": method,
                    "host": host,
                    "path": parsed.path,
                    "status": status,
                    "resource_type": res_type,
                })

        return {
            "total_requests": len(records),
            "unique_domains_count": len(domains),
            "domains": domains,
            "methods": methods,
            "status_distribution": statuses,
            "api_endpoints_detected": len(api_endpoints),
            "api_endpoints": api_endpoints[:50],
        }

