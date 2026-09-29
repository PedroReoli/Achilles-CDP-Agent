"""CLI for browser-owned bookmarks."""

import json
import sys
from typing import Any, Dict

from achilles.services.application import ApplicationServices
from achilles.services.errors import ServiceError


async def run_bookmarks(cdp_port: int, operation: str, arguments: Dict[str, Any]) -> None:
    services = ApplicationServices(cdp_port)
    try:
        result = await services.call("browser_bookmarks_" + operation, arguments)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except ServiceError as exc:
        print(json.dumps({"error": exc.as_dict()}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1) from None
    finally:
        await services.close()
