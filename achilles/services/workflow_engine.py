"""Executor declarativo com checkpoint, retomada e exportação de resultados."""

import csv
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .application import ApplicationServices
from .errors import ServiceError
from .named_sessions import achilles_data_dir

STEP_TO_TOOL = {
    "navigate": "browser_navigate",
    "wait_for": "browser_wait_for_state",
    "find_and_act": "browser_find_and_act",
    "fill_form": "browser_fill_form",
    "extract": "browser_extract",
    "extract_paginated": "browser_extract_paginated",
    "screenshot": "browser_screenshot",
    "upload": "browser_upload",
    "download": "browser_download",
    "dialog": "browser_handle_dialog",
    "wait_challenge": "browser_wait_for_challenge",
}


def load_workflow(path: str) -> Dict[str, Any]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ServiceError("WORKFLOW_NOT_FOUND", "Arquivo de workflow não encontrado.")
    if source.stat().st_size > 1024 * 1024:
        raise ServiceError("WORKFLOW_TOO_LARGE", "Workflow limitado a 1 MiB.")
    raw = source.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw) if source.suffix.lower() == ".json" else yaml.safe_load(raw)
    except (ValueError, yaml.YAMLError) as exc:
        raise ServiceError("WORKFLOW_INVALID", "Workflow JSON/YAML inválido.") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("steps"), list):
        raise ServiceError("WORKFLOW_INVALID", "Workflow precisa conter uma lista steps.")
    return payload


class WorkflowEngine:
    def __init__(self, services: ApplicationServices) -> None:
        self.services = services
        self.root = achilles_data_dir() / "runs"
        self.root.mkdir(parents=True, exist_ok=True)

    def _save(self, state: Dict[str, Any]) -> None:
        path = Path(state["checkpoint"])
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def _resolve(self, value: Any, variables: Dict[str, Any]) -> Any:
        if isinstance(value, dict):
            return {key: self._resolve(item, variables) for key, item in value.items()}
        if isinstance(value, list):
            return [self._resolve(item, variables) for item in value]
        if not isinstance(value, str):
            return value
        pattern = re.compile(r"\$\{([A-Z][A-Z0-9_]*)\}")

        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            resolved = variables.get(key, os.environ.get(f"ACHILLES_VAR_{key}"))
            if resolved is None:
                raise ServiceError(
                    "WORKFLOW_INPUT_REQUIRED",
                    f"Defina ACHILLES_VAR_{key} para executar o workflow.",
                )
            return str(resolved)

        return pattern.sub(replace, value)

    async def execute(
        self,
        workflow: Dict[str, Any],
        run_id: Optional[str] = None,
        resume: bool = False,
    ) -> Dict[str, Any]:
        identifier = run_id or uuid.uuid4().hex
        checkpoint = self.root / f"{identifier}.json"
        if resume:
            if not checkpoint.is_file():
                raise ServiceError("CHECKPOINT_NOT_FOUND", "Checkpoint não encontrado.")
            state = json.loads(checkpoint.read_text(encoding="utf-8"))
        else:
            state = {
                "run_id": identifier,
                "name": workflow.get("name", "workflow"),
                "status": "running",
                "next_step": 0,
                "results": [],
                "started_at": time.time(),
                "checkpoint": str(checkpoint),
            }
            self._save(state)
        steps = workflow["steps"]
        variables = workflow.get("variables", {})
        if not isinstance(variables, dict):
            raise ServiceError("WORKFLOW_INVALID", "variables precisa ser um objeto.")
        for index in range(int(state["next_step"]), len(steps)):
            step = steps[index]
            if not isinstance(step, dict) or len(step) != 1:
                raise ServiceError("WORKFLOW_INVALID", f"Passo {index + 1} deve ter uma operação.")
            operation, arguments = next(iter(step.items()))
            if operation == "export":
                result = self.export(state["results"], arguments or {})
            else:
                tool = STEP_TO_TOOL.get(operation)
                if not tool:
                    raise ServiceError("WORKFLOW_INVALID", f"Operação não permitida: {operation}")
                if isinstance(arguments, str):
                    arguments = {"url": arguments} if operation == "navigate" else {"text": arguments}
                if not isinstance(arguments, dict):
                    raise ServiceError("WORKFLOW_INVALID", f"Argumentos inválidos no passo {index + 1}.")
                arguments = self._resolve(arguments, variables)
                result = await self.services.call(tool, arguments)
            state["results"].append({"step": index + 1, "operation": operation, "result": result})
            state["next_step"] = index + 1
            self._save(state)
        state["status"] = "completed"
        state["completed_at"] = time.time()
        self._save(state)
        return state

    def export(self, results: List[Dict[str, Any]], options: Dict[str, Any]) -> Dict[str, Any]:
        output = Path(options.get("path", self.root / f"export-{uuid.uuid4().hex}.jsonl")).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        records = []
        for entry in results:
            result = entry.get("result", {})
            records.extend(result.get("items", []))
        fmt = options.get("format", output.suffix.lstrip(".") or "jsonl").lower()
        if fmt == "json":
            output.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        elif fmt == "jsonl":
            output.write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records),
                encoding="utf-8",
            )
        elif fmt == "csv":
            fields = sorted({key for row in records for key in row})
            with output.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(records)
        else:
            raise ServiceError("WORKFLOW_INVALID", "Formato de exportação deve ser json, jsonl ou csv.")
        return {"path": str(output), "format": fmt, "records": len(records)}
