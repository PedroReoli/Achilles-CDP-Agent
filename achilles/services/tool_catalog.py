"""Metadados MCP compartilhados sem acoplar contratos a transportes."""

from typing import Any, Dict, Optional, Type

from pydantic import BaseModel

from .desktop_contracts import (
    DESKTOP_DESTRUCTIVE,
    DESKTOP_MUTATING,
    DESKTOP_NON_IDEMPOTENT,
)

BROWSER_MUTATING = {
    "browser_select_page", "browser_new_tab", "browser_close_tab", "browser_navigate",
    "browser_scroll", "browser_action", "browser_find_and_act", "browser_fill_form",
    "browser_upload", "browser_download", "browser_handle_dialog", "browser_recording",
    "browser_domain_memory", "browser_export_html_report", "browser_bookmarks_create",
    "browser_bookmarks_update", "browser_bookmarks_remove",
}
BROWSER_DESTRUCTIVE = {
    "browser_action", "browser_find_and_act", "browser_fill_form", "browser_close_tab",
    "browser_bookmarks_remove",
}
BROWSER_NON_IDEMPOTENT = {
    "browser_action", "browser_find_and_act", "browser_fill_form", "browser_download",
    "browser_handle_dialog", "browser_new_tab", "browser_close_tab",
    "browser_bookmarks_create", "browser_bookmarks_remove",
}

OUTPUT_SCHEMAS = {
    "browser_status": {
        "type": "object",
        "properties": {
            "cdp_url": {"type": "string"}, "mode": {"type": "string"},
            "generation": {"type": "integer"}, "recorded_requests": {"type": "integer"},
            "dropped_events": {"type": "integer"},
        },
        "required": ["cdp_url", "mode", "generation", "recorded_requests"],
    },
    "browser_find": {
        "type": "object",
        "properties": {
            "page_id": {"type": "string"}, "snapshot_id": {"type": "string"},
            "query": {"type": "string"}, "matches": {"type": "array", "items": {"type": "object"}},
            "match_count": {"type": "integer"}, "truncated": {"type": "boolean"},
        },
        "required": ["page_id", "snapshot_id", "query", "matches", "match_count"],
    },
    "browser_extract": {
        "type": "object",
        "properties": {
            "page_id": {"type": "string"}, "url": {"type": "string"},
            "items": {"type": "array", "items": {"type": "object"}},
            "count": {"type": "integer"}, "truncated": {"type": "boolean"},
        },
        "required": ["page_id", "url", "items", "count", "truncated"],
    },
    "browser_action": {
        "type": "object",
        "properties": {
            "status": {"type": "string"}, "action": {"type": "string"},
            "page_id": {"type": "string"}, "url_after": {"type": "string"},
            "duration_ms": {"type": "number"}, "verification": {"type": "object"},
        },
        "required": ["status", "action", "page_id", "duration_ms", "verification"],
    },
    "app_status": {
        "type": "object",
        "properties": {
            "supported": {"type": "boolean"}, "platform": {"type": "string"},
            "backend": {"type": "string"}, "semantic_actions": {"type": "boolean"},
            "visual_fallback": {"type": "boolean"},
        },
        "required": ["supported", "platform", "backend"],
    },
}


def build_tool_catalog(
    contracts: Dict[str, Type[BaseModel]],
    descriptions: Dict[str, str],
    allowed_names: Optional[set] = None,
) -> Dict[str, Any]:
    mutating = BROWSER_MUTATING | DESKTOP_MUTATING
    destructive = BROWSER_DESTRUCTIVE | DESKTOP_DESTRUCTIVE
    non_idempotent = BROWSER_NON_IDEMPOTENT | DESKTOP_NON_IDEMPOTENT
    tools = []
    for name, contract in contracts.items():
        if allowed_names is not None and name not in allowed_names:
            continue
        tool = {
            "name": name,
            "description": descriptions[name],
            "inputSchema": contract.model_json_schema(),
            "annotations": {
                "readOnlyHint": name not in mutating,
                "destructiveHint": name in destructive,
                "idempotentHint": name not in non_idempotent,
                "openWorldHint": name.startswith(("browser_", "network_", "app_")),
            },
        }
        if name in OUTPUT_SCHEMAS:
            tool["outputSchema"] = OUTPUT_SCHEMAS[name]
        tools.append(tool)
    return {"tools": tools}
