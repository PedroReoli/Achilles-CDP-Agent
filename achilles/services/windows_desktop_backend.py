"""Backend síncrono Windows UI Automation executado em uma thread COM dedicada."""

import ctypes
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .errors import ServiceError
from .named_sessions import achilles_data_dir

PROTECTED_EXECUTABLES = {
    "consent.exe",
    "credentialuibroker.exe",
    "lsass.exe",
    "logonui.exe",
    "winlogon.exe",
}


def _rect_dict(rect: Any) -> Dict[str, int]:
    return {
        "left": int(rect.left),
        "top": int(rect.top),
        "right": int(rect.right),
        "bottom": int(rect.bottom),
        "width": max(0, int(rect.right - rect.left)),
        "height": max(0, int(rect.bottom - rect.top)),
    }


def _process_image(process_id: int) -> str:
    if sys.platform != "win32":
        return ""
    process_query_limited_information = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(
        process_query_limited_information, False, process_id
    )
    if not handle:
        return ""
    try:
        size = ctypes.c_ulong(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if ctypes.windll.kernel32.QueryFullProcessImageNameW(
            handle, 0, buffer, ctypes.byref(size)
        ):
            return buffer.value
        return ""
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


class WindowsDesktopBackend:
    """Mantém objetos UIA e snapshots na mesma thread para respeitar o apartment COM."""

    def __init__(self, policy: Any = None) -> None:
        self.policy = policy
        self.selected_handle: Optional[int] = None
        self.snapshots: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        self.screenshots: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        self._desktop_type: Any = None
        self._mouse: Any = None

    def _load(self) -> None:
        if sys.platform != "win32":
            raise ServiceError("DESKTOP_UNSUPPORTED", "O runtime de desktop suporta somente Windows.")
        if self._desktop_type is not None:
            return
        try:
            from pywinauto import Desktop, mouse
        except ImportError as exc:
            raise ServiceError(
                "DESKTOP_RUNTIME_UNAVAILABLE",
                "Instale o Achilles com as dependências Windows para controlar aplicativos.",
                recovery={"command": "pip install -U achilles-cdp"},
            ) from exc
        self._desktop_type = Desktop
        self._mouse = mouse

    def status(self) -> Dict[str, Any]:
        if sys.platform != "win32":
            return {
                "supported": False,
                "platform": sys.platform,
                "backend": "unavailable",
                "reason": "O runtime de aplicativos suporta somente Windows.",
            }
        self._load()
        return {
            "supported": True,
            "platform": "windows",
            "backend": "uia",
            "selected_window_handle": self.selected_handle,
            "semantic_actions": True,
            "visual_fallback": True,
            "secure_desktop_supported": False,
        }

    def _desktop(self) -> Any:
        self._load()
        return self._desktop_type(backend="uia")

    @staticmethod
    def _window_payload(window: Any) -> Dict[str, Any]:
        info = window.element_info
        process_id = int(info.process_id or 0)
        executable = _process_image(process_id)
        return {
            "app_id": f"app-{process_id}",
            "process_id": process_id,
            "executable": executable,
            "executable_name": Path(executable).name if executable else "",
            "window_id": f"window-{int(info.handle):x}",
            "window_handle": int(info.handle),
            "title": str(info.name or ""),
            "class_name": str(info.class_name or ""),
            "control_type": str(info.control_type or "Window"),
            "visible": bool(window.is_visible()),
            "enabled": bool(window.is_enabled()),
            "bounds": _rect_dict(info.rectangle),
        }

    def _top_windows(self, visible_only: bool = True) -> List[Any]:
        try:
            return list(self._desktop().windows(visible_only=visible_only, top_level_only=True))
        except Exception as exc:
            raise ServiceError(
                "DESKTOP_ENUMERATION_FAILED",
                "Não foi possível enumerar as janelas da sessão interativa.",
            ) from exc

    def list_windows(self, visible_only: bool = True, limit: int = 100) -> Dict[str, Any]:
        windows = []
        for window in self._top_windows(visible_only):
            try:
                item = self._window_payload(window)
                if item["process_id"] <= 0 or item["bounds"]["width"] <= 0:
                    continue
                item["selected"] = item["window_handle"] == self.selected_handle
                windows.append(item)
                if len(windows) >= limit:
                    break
            except Exception:
                continue
        return {"windows": windows, "count": len(windows), "truncated": len(windows) >= limit}

    def list_apps(self, visible_only: bool = True, limit: int = 100) -> Dict[str, Any]:
        rows = self.list_windows(visible_only, min(500, limit * 10))["windows"]
        grouped: Dict[int, Dict[str, Any]] = {}
        for row in rows:
            app = grouped.setdefault(
                row["process_id"],
                {
                    "app_id": row["app_id"],
                    "process_id": row["process_id"],
                    "executable": row["executable"],
                    "executable_name": row["executable_name"],
                    "windows": [],
                },
            )
            app["windows"].append(
                {
                    key: row[key]
                    for key in ("window_id", "window_handle", "title", "bounds", "selected")
                }
            )
        apps = list(grouped.values())[:limit]
        return {"apps": apps, "count": len(apps), "truncated": len(grouped) > limit}

    @staticmethod
    def _matches_window(window: Any, target: Dict[str, Any]) -> bool:
        info = window.element_info
        if target.get("window_handle") and int(info.handle) != target["window_handle"]:
            return False
        if target.get("process_id") and int(info.process_id) != target["process_id"]:
            return False
        title = str(info.name or "")
        if target.get("title") and target["title"].casefold() not in title.casefold():
            return False
        executable = _process_image(int(info.process_id or 0))
        requested = target.get("executable")
        if requested:
            requested_folded = requested.casefold()
            if requested_folded not in (executable.casefold(), Path(executable).name.casefold()):
                return False
        return True

    def _resolve_window(self, target: Dict[str, Any]) -> Any:
        effective = {key: value for key, value in target.items() if value is not None}
        if not any(effective.get(key) for key in ("process_id", "window_handle", "title", "executable")):
            if self.selected_handle:
                effective["window_handle"] = self.selected_handle
            else:
                raise ServiceError(
                    "APP_NOT_ATTACHED",
                    "Selecione uma janela com app_attach ou informe um alvo explícito.",
                )
        elif self.selected_handle and not effective.get("window_handle"):
            try:
                selected = self._desktop().window(handle=self.selected_handle)
                if self._matches_window(selected, effective):
                    return selected
            except Exception:
                self.selected_handle = None
        for window in self._top_windows(False):
            try:
                if self._matches_window(window, effective):
                    return window
            except Exception:
                continue
        raise ServiceError("APP_NOT_FOUND", "Aplicativo ou janela não encontrado.")

    def _authorize(self, tool: str, window: Any) -> None:
        payload = self._window_payload(window)
        executable_name = payload["executable_name"].casefold()
        if executable_name in PROTECTED_EXECUTABLES:
            raise ServiceError(
                "PROTECTED_APP",
                "O Achilles não controla credenciais, logon ou a área de trabalho segura.",
            )
        if self.policy is not None:
            self.policy.check_desktop(tool, payload["executable"], payload["title"])

    def attach(self, **target: Any) -> Dict[str, Any]:
        window = self._resolve_window(target)
        self._authorize("app_attach", window)
        self.selected_handle = int(window.element_info.handle)
        payload = self._window_payload(window)
        payload["attached"] = True
        return payload

    @staticmethod
    def _resolve_executable(value: str) -> Path:
        expanded = os.path.expandvars(os.path.expanduser(value))
        candidate = Path(expanded)
        if candidate.is_absolute() or candidate.parent != Path("."):
            resolved = candidate.resolve()
            if not resolved.is_file():
                raise ServiceError("EXECUTABLE_NOT_FOUND", "Executável não encontrado.")
        else:
            discovered = shutil.which(expanded)
            if not discovered:
                raise ServiceError("EXECUTABLE_NOT_FOUND", "Executável não encontrado no PATH.")
            resolved = Path(discovered).resolve()
        if resolved.suffix.casefold() not in (".exe", ".com"):
            raise ServiceError("EXECUTABLE_NOT_ALLOWED", "Somente executáveis .exe ou .com são aceitos.")
        return resolved

    def launch(
        self,
        executable: Optional[str],
        app_user_model_id: Optional[str],
        uri: Optional[str],
        arguments: List[str],
        cwd: Optional[str],
        window_title: Optional[str],
        timeout_ms: int,
    ) -> Dict[str, Any]:
        requested_identity: str
        launched_executable: Path
        launched_arguments: List[str]
        expected_image = ""
        if executable:
            launched_executable = self._resolve_executable(executable)
            launched_arguments = arguments
            requested_identity = str(launched_executable)
            expected_image = launched_executable.name.casefold()
        else:
            explorer = shutil.which("explorer.exe")
            if not explorer:
                raise ServiceError("EXECUTABLE_NOT_FOUND", "explorer.exe não foi encontrado.")
            launched_executable = Path(explorer).resolve()
            if app_user_model_id:
                if not re.fullmatch(r"[A-Za-z0-9._!\-]{1,512}", app_user_model_id):
                    raise ServiceError("INVALID_APP_ID", "AUMID contém caracteres inválidos.")
                requested_identity = app_user_model_id
                launched_arguments = [f"shell:AppsFolder\\{app_user_model_id}"]
            else:
                assert uri is not None
                scheme = uri.split(":", 1)[0].casefold() if ":" in uri else ""
                if not re.fullmatch(r"[a-z][a-z0-9+.-]{1,31}", scheme):
                    raise ServiceError("INVALID_URI", "Protocolo Windows inválido.")
                if scheme in ("file", "javascript", "data", "http", "https"):
                    raise ServiceError("INVALID_URI", "Esse protocolo não é permitido em app_launch.")
                requested_identity = uri
                launched_arguments = [uri]
        if self.policy is not None:
            self.policy.check_desktop("app_launch", requested_identity, "")
        working_directory = None
        if cwd:
            working_directory = Path(cwd).expanduser().resolve()
            if not working_directory.is_dir():
                raise ServiceError("INVALID_DIRECTORY", "O diretório de trabalho não existe.")
        before = {
            int(window.element_info.handle)
            for window in self._top_windows(False)
            if getattr(window.element_info, "handle", None)
        }
        try:
            process = subprocess.Popen(
                [str(launched_executable), *launched_arguments],
                cwd=str(working_directory) if working_directory else None,
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
        except OSError as exc:
            raise ServiceError("APP_LAUNCH_FAILED", "O Windows recusou iniciar o aplicativo.") from exc
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            for window in self._top_windows(False):
                try:
                    info = window.element_info
                    same_process = int(info.process_id) == process.pid
                    is_new = int(info.handle) not in before
                    title_matches = (
                        window_title is not None
                        and window_title.casefold() in str(info.name or "").casefold()
                    )
                    image_matches = (
                        Path(_process_image(int(info.process_id or 0))).name.casefold()
                        == expected_image
                    )
                    matches_requested_window = (
                        title_matches
                        if window_title
                        else same_process or is_new and (image_matches or not expected_image)
                    )
                    if matches_requested_window:
                        self._authorize("app_launch", window)
                        self.selected_handle = int(window.element_info.handle)
                        payload = {"launched": True, **self._window_payload(window)}
                        self._detach_process(process)
                        return payload
                except Exception:
                    continue
            if process.poll() is not None:
                break
            time.sleep(0.1)
        running = process.poll() is None
        if running:
            self._detach_process(process)
        return {
            "launched": running,
            "process_id": process.pid,
            "executable": str(launched_executable),
            "requested_target": requested_identity,
            "window": None,
        }

    @staticmethod
    def _detach_process(process: subprocess.Popen) -> None:
        """Fecha apenas o handle local; o aplicativo iniciado continua independente."""
        handle = getattr(process, "_handle", None)
        if handle is not None:
            handle.Close()
            process._handle = None
        process.returncode = 0

    @staticmethod
    def _element_payload(index: int, wrapper: Any) -> Dict[str, Any]:
        info = wrapper.element_info
        control_type = str(info.control_type or "Custom")
        is_password = bool(getattr(info, "is_password", False))
        name = "[REDACTED]" if is_password else str(info.name or "")
        return {
            "element_ref": f"element-{index}",
            "name": name,
            "role": control_type,
            "automation_id": str(info.automation_id or ""),
            "class_name": str(info.class_name or ""),
            "enabled": bool(wrapper.is_enabled()),
            "visible": bool(wrapper.is_visible()),
            "focused": bool(wrapper.has_keyboard_focus()),
            "sensitive": is_password,
            "bounds": _rect_dict(info.rectangle),
        }

    def snapshot(
        self,
        limit: int = 300,
        visible_only: bool = True,
        **target: Any,
    ) -> Dict[str, Any]:
        window = self._resolve_window(target)
        self._authorize("app_snapshot", window)
        wrappers: Iterable[Any] = [window, *window.descendants()]
        elements = []
        live = {}
        for wrapper in wrappers:
            if len(elements) >= limit:
                break
            try:
                payload = self._element_payload(len(elements) + 1, wrapper)
                if visible_only and not payload["visible"]:
                    continue
                elements.append(payload)
                live[payload["element_ref"]] = wrapper
            except Exception:
                continue
        snapshot_id = "desktop-" + uuid.uuid4().hex
        record = {
            "created_at": time.monotonic(),
            "window_handle": int(window.element_info.handle),
            "window_bounds": _rect_dict(window.element_info.rectangle),
            "elements": live,
        }
        self.snapshots[snapshot_id] = record
        while len(self.snapshots) > 20:
            self.snapshots.popitem(last=False)
        return {
            "snapshot_id": snapshot_id,
            "window": self._window_payload(window),
            "elements": elements,
            "count": len(elements),
            "truncated": len(elements) >= limit,
            "source": "windows_uia",
        }

    def find(
        self,
        query: str,
        role: Optional[str] = None,
        limit: int = 20,
        **target: Any,
    ) -> Dict[str, Any]:
        result = self.snapshot(limit=2000, visible_only=True, **target)
        needle = query.casefold()
        role_folded = role.casefold() if role else None
        matches = []
        for element in result["elements"]:
            haystack = " ".join(
                (element["name"], element["automation_id"], element["class_name"])
            ).casefold()
            if needle not in haystack:
                continue
            if role_folded and role_folded != element["role"].casefold():
                continue
            matches.append(element)
            if len(matches) >= limit:
                break
        return {
            "snapshot_id": result["snapshot_id"],
            "window": result["window"],
            "query": query,
            "matches": matches,
            "match_count": len(matches),
            "truncated": len(matches) >= limit,
        }

    def _snapshot_element(self, snapshot_id: str, element_ref: str) -> Tuple[Any, Dict[str, Any]]:
        record = self.snapshots.get(snapshot_id)
        if record is None or time.monotonic() - record["created_at"] > 60:
            raise ServiceError("STALE_ELEMENT_REF", "Snapshot de desktop expirado; capture outro.")
        wrapper = record["elements"].get(element_ref)
        if wrapper is None:
            raise ServiceError("ELEMENT_NOT_FOUND", "Referência de elemento inexistente.")
        try:
            wrapper.element_info.rectangle
        except Exception as exc:
            raise ServiceError("STALE_ELEMENT_REF", "O controle não está mais acessível.") from exc
        self._authorize("app_action", self._desktop().window(handle=record["window_handle"]))
        return wrapper, record

    @staticmethod
    def _semantic_action(wrapper: Any, action: str, value: Optional[str]) -> None:
        if action == "click":
            try:
                wrapper.iface_invoke.Invoke()
            except Exception:
                wrapper.click()
        elif action == "double_click":
            wrapper.double_click()
        elif action == "right_click":
            wrapper.right_click()
        elif action == "focus":
            wrapper.set_focus()
        elif action == "fill":
            wrapper.set_edit_text(value or "")
        elif action == "press":
            wrapper.type_keys(value or "", with_spaces=True, set_foreground=True)
        elif action == "select":
            wrapper.select(value)
        elif action == "toggle":
            wrapper.toggle()
        elif action == "expand":
            wrapper.expand()
        elif action == "collapse":
            wrapper.collapse()

    def _mouse_action(self, action: str, point: Tuple[int, int]) -> None:
        if action == "double_click":
            self._mouse.double_click(button="left", coords=point)
        else:
            self._mouse.click(
                button="right" if action == "right_click" else "left",
                coords=point,
            )

    def action(
        self,
        action: str,
        snapshot_id: str,
        element_ref: str,
        value: Optional[str],
        allow_coordinate_fallback: bool,
    ) -> Dict[str, Any]:
        wrapper, _ = self._snapshot_element(snapshot_id, element_ref)
        started = time.perf_counter()
        mode = "semantic"
        try:
            self._semantic_action(wrapper, action, value)
        except Exception as exc:
            if not allow_coordinate_fallback or action not in ("click", "double_click", "right_click"):
                raise ServiceError(
                    "ACTION_UNSUPPORTED",
                    "O controle não oferece esse padrão semântico; permita fallback por coordenada.",
                ) from exc
            rect = wrapper.element_info.rectangle
            point = (int((rect.left + rect.right) / 2), int((rect.top + rect.bottom) / 2))
            self._mouse_action(action, point)
            mode = "coordinate_fallback"
        return {
            "status": "ok",
            "action": action,
            "snapshot_id": snapshot_id,
            "element_ref": element_ref,
            "mode": mode,
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
        }

    def find_and_act(self, query: str, role: Optional[str], action: str, value: Optional[str],
                     allow_coordinate_fallback: bool, **target: Any) -> Dict[str, Any]:
        found = self.find(query=query, role=role, limit=20, **target)
        if not found["matches"]:
            raise ServiceError("ELEMENT_NOT_FOUND", f"Nenhum controle corresponde a '{query}'.")
        exact = [row for row in found["matches"] if row["name"].casefold() == query.casefold()]
        selected = (exact or found["matches"])[0]
        result = self.action(
            action, found["snapshot_id"], selected["element_ref"], value,
            allow_coordinate_fallback,
        )
        result["matched"] = selected
        return result

    def fill_form(self, fields: Dict[str, str], submit_query: Optional[str],
                  allow_coordinate_fallback: bool, **target: Any) -> Dict[str, Any]:
        completed = []
        for query, value in fields.items():
            result = self.find_and_act(
                query=query,
                role="Edit",
                action="fill",
                value=value,
                allow_coordinate_fallback=False,
                **target,
            )
            completed.append({"query": query, "status": result["status"]})
        submitted = False
        if submit_query:
            self.find_and_act(
                query=submit_query,
                role="Button",
                action="click",
                value=None,
                allow_coordinate_fallback=allow_coordinate_fallback,
                **target,
            )
            submitted = True
        return {"status": "ok", "fields": completed, "submitted": submitted}

    def wait_for_state(self, query: Optional[str], role: Optional[str], state: str,
                       timeout_ms: int, **target: Any) -> Dict[str, Any]:
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            try:
                if query:
                    found = self.find(query=query, role=role, limit=1, **target)
                    match = found["matches"][0] if found["matches"] else None
                    reached = state == "not_exists" if match is None else (
                        state == "exists"
                        or state == "visible" and match["visible"]
                        or state == "enabled" and match["enabled"]
                        or state == "focused" and match["focused"]
                    )
                else:
                    window = self._resolve_window(target)
                    reached = state != "not_exists" and (
                        state == "exists"
                        or state == "visible" and window.is_visible()
                        or state == "enabled" and window.is_enabled()
                        or state == "focused" and window.has_keyboard_focus()
                    )
            except ServiceError as exc:
                reached = state == "not_exists" and exc.code == "APP_NOT_FOUND"
            if reached:
                return {"status": "reached", "state": state, "query": query}
            time.sleep(0.2)
        raise ServiceError("WAIT_TIMEOUT", "O estado esperado não foi observado no prazo.")

    def screenshot(self, image_format: str, **target: Any) -> Dict[str, Any]:
        window = self._resolve_window(target)
        self._authorize("app_screenshot", window)
        screenshot_id = "screen-" + uuid.uuid4().hex
        extension = "jpg" if image_format == "jpeg" else "png"
        output = achilles_data_dir() / "artifacts" / f"{screenshot_id}.{extension}"
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            window.set_focus()
            time.sleep(0.15)
            image = window.capture_as_image()
            save_format = "JPEG" if image_format == "jpeg" else "PNG"
            image.save(output, format=save_format)
        except Exception as exc:
            raise ServiceError("SCREENSHOT_FAILED", "Não foi possível capturar a janela.") from exc
        bounds = _rect_dict(window.element_info.rectangle)
        record = {
            "created_at": time.monotonic(),
            "window_handle": int(window.element_info.handle),
            "bounds": bounds,
        }
        self.screenshots[screenshot_id] = record
        while len(self.screenshots) > 20:
            self.screenshots.popitem(last=False)
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        return {
            "screenshot_id": screenshot_id,
            "path": str(output),
            "format": image_format,
            "sha256": digest,
            "bytes": output.stat().st_size,
            "window": self._window_payload(window),
        }

    def click_at(self, screenshot_id: str, x: int, y: int, action: str) -> Dict[str, Any]:
        record = self.screenshots.get(screenshot_id)
        if record is None or time.monotonic() - record["created_at"] > 30:
            raise ServiceError("STALE_SCREENSHOT", "Screenshot expirado; capture outro antes de agir.")
        window = self._resolve_window({"window_handle": record["window_handle"]})
        self._authorize("app_click_at", window)
        window.set_focus()
        time.sleep(0.05)
        current = _rect_dict(window.element_info.rectangle)
        if current != record["bounds"]:
            raise ServiceError("STALE_SCREENSHOT", "A janela mudou desde o screenshot.")
        if x >= current["width"] or y >= current["height"]:
            raise ServiceError("INVALID_COORDINATES", "A coordenada está fora da janela.")
        point = (current["left"] + x, current["top"] + y)
        if action == "hover":
            self._mouse.move(coords=point)
        else:
            self._mouse_action(action, point)
        return {
            "status": "ok",
            "action": action,
            "screenshot_id": screenshot_id,
            "relative_coordinates": {"x": x, "y": y},
        }

    def close_window(self, timeout_ms: int, **target: Any) -> Dict[str, Any]:
        window = self._resolve_window(target)
        self._authorize("app_close", window)
        handle = int(window.element_info.handle)
        window.close()
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            if not any(int(item.element_info.handle) == handle for item in self._top_windows(False)):
                if self.selected_handle == handle:
                    self.selected_handle = None
                return {"closed": True, "window_handle": handle, "forced": False}
            time.sleep(0.1)
        return {"closed": False, "window_handle": handle, "forced": False}
