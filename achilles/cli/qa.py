"""Comandos enxutos para o runtime de QA."""

import json
import sys
from typing import Any, Dict

from achilles.services.application import ApplicationServices


async def run_qa(operation: str, cdp_port: int, values: Dict[str, Any]) -> None:
    services = ApplicationServices(cdp_port)
    try:
        if operation == "discover":
            tool = "qa_discover"
            arguments = {
                "openapi": values.get("openapi"),
                "base_url": values.get("base_url"),
                "include_traffic": values.get("include_traffic", True),
                "limit": values.get("limit", 200),
            }
        elif operation == "request":
            tool = "qa_request"
            arguments = {
                "method": values["method"],
                "url": values["url"],
                "expected_status": values["expected_status"],
                "timeout_ms": values["timeout_ms"],
                "allow_mutating": values.get("allow_mutating", False),
            }
        elif operation == "run":
            tool = "qa_run_suite"
            arguments = {"path": values["path"], "variables": {}}
        elif operation == "report":
            tool = "qa_report"
            arguments = {
                "run_id": values.get("run_id"),
                "format": values["format"],
                "output_path": values.get("output_path"),
            }
        elif operation == "audit":
            tool = "qa_security_audit"
            arguments = {
                "urls": values.get("urls", []),
                "include_traffic": values.get("include_traffic", True),
                "timeout_ms": values["timeout_ms"],
            }
        elif operation == "runs":
            tool = "qa_runs"
            arguments = {"limit": values.get("limit", 20)}
        else:
            raise ValueError(f"Operação QA desconhecida: {operation}")
        result = await services.call(tool, arguments)
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    finally:
        await services.close()
