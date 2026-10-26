"""Contrato interno entre o processo principal e o worker de desktop."""

DESKTOP_METHODS = {
    "app_status": "status",
    "app_list": "list_apps",
    "app_launch": "launch",
    "app_attach": "attach",
    "app_windows": "list_windows",
    "app_snapshot": "snapshot",
    "app_find": "find",
    "app_action": "action",
    "app_find_and_act": "find_and_act",
    "app_fill_form": "fill_form",
    "app_wait_for_state": "wait_for_state",
    "app_screenshot": "screenshot",
    "app_click_at": "click_at",
    "app_close": "close_window",
}

MAX_WORKER_MESSAGE = 2 * 1024 * 1024
