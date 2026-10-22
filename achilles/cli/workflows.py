"""CLI JSON para workflows e missões."""

import json
import time
import uuid
from pathlib import Path
from typing import Optional

from achilles.services.application import ApplicationServices
from achilles.services.errors import ServiceError
from achilles.services.named_sessions import achilles_data_dir
from achilles.services.workflow_engine import WorkflowEngine, load_workflow


async def run_workflow(path: str, cdp_port: int, run_id: Optional[str], resume: bool) -> None:
    services = ApplicationServices(cdp_port)
    try:
        result = await WorkflowEngine(services).execute(load_workflow(path), run_id, resume)
        print(json.dumps({"ok": True, **result}, ensure_ascii=False))
    except ServiceError as exc:
        print(json.dumps({"ok": False, "error": exc.as_dict()}, ensure_ascii=False))
        raise SystemExit(1) from None
    finally:
        await services.close()


async def run_mission(
    objective: str,
    cdp_port: int,
    workflow_path: Optional[str] = None,
    run_id: Optional[str] = None,
    resume: bool = False,
) -> None:
    mission_id = run_id or uuid.uuid4().hex
    mission_dir = achilles_data_dir() / "missions"
    mission_dir.mkdir(parents=True, exist_ok=True)
    mission_path = mission_dir / f"{mission_id}.json"
    mission = {
        "mission_id": mission_id,
        "objective": objective,
        "status": "running" if workflow_path else "awaiting_plan",
        "created_at": time.time(),
        "workflow": str(Path(workflow_path).resolve()) if workflow_path else None,
    }
    mission_path.write_text(json.dumps(mission, ensure_ascii=False, indent=2), encoding="utf-8")
    if not workflow_path:
        print(json.dumps({
            "ok": True,
            **mission,
            "message": "Missão registrada. Forneça --workflow para execução determinística por um agente.",
            "mission_path": str(mission_path),
        }, ensure_ascii=False))
        return
    services = ApplicationServices(cdp_port)
    try:
        result = await WorkflowEngine(services).execute(load_workflow(workflow_path), mission_id, resume)
        mission.update({"status": result["status"], "run": result, "completed_at": time.time()})
        mission_path.write_text(json.dumps(mission, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": True, **mission, "mission_path": str(mission_path)}, ensure_ascii=False))
    except ServiceError as exc:
        mission.update({"status": "failed", "error": exc.as_dict()})
        mission_path.write_text(json.dumps(mission, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": False, **mission}, ensure_ascii=False))
        raise SystemExit(1) from None
    finally:
        await services.close()
