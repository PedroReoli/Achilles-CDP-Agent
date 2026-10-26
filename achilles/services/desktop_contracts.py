"""Contratos públicos do runtime de automação de desktop Windows."""

from typing import Dict, List, Literal, Optional, Type

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DesktopArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class DesktopTargetArguments(DesktopArguments):
    process_id: Optional[int] = Field(None, ge=1)
    window_handle: Optional[int] = Field(None, ge=1)
    title: Optional[str] = Field(None, min_length=1, max_length=512)
    executable: Optional[str] = Field(None, min_length=1, max_length=2048)


class AppListArguments(DesktopArguments):
    visible_only: bool = True
    limit: int = Field(100, ge=1, le=500)


class AppLaunchArguments(DesktopArguments):
    executable: Optional[str] = Field(None, min_length=1, max_length=2048)
    app_user_model_id: Optional[str] = Field(None, min_length=1, max_length=512)
    uri: Optional[str] = Field(None, min_length=1, max_length=2048)
    arguments: List[str] = Field(default_factory=list, max_length=100)
    cwd: Optional[str] = Field(None, min_length=1, max_length=2048)
    window_title: Optional[str] = Field(None, min_length=1, max_length=512)
    timeout_ms: int = Field(10000, ge=500, le=60000)

    @model_validator(mode="after")
    def launch_target_required(self) -> "AppLaunchArguments":
        if sum(value is not None for value in (self.executable, self.app_user_model_id, self.uri)) != 1:
            raise ValueError("Informe exatamente um: executable, app_user_model_id ou uri")
        if self.arguments and self.executable is None:
            raise ValueError("arguments só é permitido com executable")
        return self


class AppAttachArguments(DesktopTargetArguments):
    @model_validator(mode="after")
    def target_required(self) -> "AppAttachArguments":
        if not any((self.process_id, self.window_handle, self.title, self.executable)):
            raise ValueError("Informe process_id, window_handle, title ou executable")
        return self


class AppSnapshotArguments(DesktopTargetArguments):
    limit: int = Field(300, ge=1, le=2000)
    visible_only: bool = True


class AppFindArguments(DesktopTargetArguments):
    query: str = Field(min_length=1, max_length=512)
    role: Optional[str] = Field(None, min_length=1, max_length=128)
    limit: int = Field(20, ge=1, le=100)


class AppActionArguments(DesktopArguments):
    action: Literal[
        "click",
        "double_click",
        "right_click",
        "focus",
        "fill",
        "press",
        "select",
        "toggle",
        "expand",
        "collapse",
    ]
    snapshot_id: str = Field(min_length=1, max_length=128)
    element_ref: str = Field(min_length=1, max_length=128)
    value: Optional[str] = Field(None, max_length=65536)
    allow_coordinate_fallback: bool = False

    @model_validator(mode="after")
    def value_required(self) -> "AppActionArguments":
        if self.action in ("fill", "press", "select") and self.value is None:
            raise ValueError("A ação exige value")
        return self


class AppFindAndActArguments(DesktopTargetArguments):
    query: str = Field(min_length=1, max_length=512)
    role: Optional[str] = Field(None, min_length=1, max_length=128)
    action: Literal[
        "click", "double_click", "right_click", "focus", "fill", "press", "select", "toggle"
    ]
    value: Optional[str] = Field(None, max_length=65536)
    allow_coordinate_fallback: bool = False

    @model_validator(mode="after")
    def value_required(self) -> "AppFindAndActArguments":
        if self.action in ("fill", "press", "select") and self.value is None:
            raise ValueError("A ação exige value")
        return self


class AppFillFormArguments(DesktopTargetArguments):
    fields: Dict[str, str] = Field(min_length=1, max_length=100)
    submit_query: Optional[str] = Field(None, min_length=1, max_length=512)
    allow_coordinate_fallback: bool = False


class AppWaitArguments(DesktopTargetArguments):
    query: Optional[str] = Field(None, min_length=1, max_length=512)
    role: Optional[str] = Field(None, min_length=1, max_length=128)
    state: Literal["exists", "not_exists", "visible", "enabled", "focused"] = "exists"
    timeout_ms: int = Field(15000, ge=100, le=120000)


class AppScreenshotArguments(DesktopTargetArguments):
    image_format: Literal["png", "jpeg"] = "png"


class AppClickAtArguments(DesktopArguments):
    screenshot_id: str = Field(min_length=1, max_length=128)
    x: int = Field(ge=0, le=100000)
    y: int = Field(ge=0, le=100000)
    action: Literal["click", "double_click", "right_click", "hover"] = "click"


class AppCloseArguments(DesktopTargetArguments):
    timeout_ms: int = Field(5000, ge=100, le=30000)


DESKTOP_CONTRACTS: Dict[str, Type[BaseModel]] = {
    "app_status": DesktopArguments,
    "app_list": AppListArguments,
    "app_launch": AppLaunchArguments,
    "app_attach": AppAttachArguments,
    "app_windows": AppListArguments,
    "app_snapshot": AppSnapshotArguments,
    "app_find": AppFindArguments,
    "app_action": AppActionArguments,
    "app_find_and_act": AppFindAndActArguments,
    "app_fill_form": AppFillFormArguments,
    "app_wait_for_state": AppWaitArguments,
    "app_screenshot": AppScreenshotArguments,
    "app_click_at": AppClickAtArguments,
    "app_close": AppCloseArguments,
}

DESKTOP_DESCRIPTIONS = {
    "app_status": "Informa disponibilidade do runtime Windows UI Automation.",
    "app_list": "Lista aplicativos de desktop com janelas acessíveis na sessão do usuário.",
    "app_launch": "Inicia um executável Windows sem shell e aguarda sua primeira janela.",
    "app_attach": "Seleciona uma janela por PID, handle, título ou executável.",
    "app_windows": "Lista janelas de desktop acessíveis e seus identificadores estáveis.",
    "app_snapshot": "Captura árvore UI Automation com referências versionadas e limites explícitos.",
    "app_find": "Localiza controles pelo nome, automation id ou papel acessível.",
    "app_action": "Executa ação semântica em uma referência de snapshot recente.",
    "app_find_and_act": "Localiza e aciona um controle em uma única chamada.",
    "app_fill_form": "Preenche vários controles acessíveis e opcionalmente envia o formulário.",
    "app_wait_for_state": "Aguarda estado observável de janela ou controle de desktop.",
    "app_screenshot": "Captura somente a janela selecionada para inspeção visual do agente.",
    "app_click_at": "Fallback visual: age em coordenada relativa de screenshot recente.",
    "app_close": "Solicita fechamento gracioso da janela selecionada; não encerra o processo à força.",
}

DESKTOP_TOOLSET = set(DESKTOP_CONTRACTS)
DESKTOP_MUTATING = {
    "app_launch", "app_attach", "app_action", "app_find_and_act", "app_fill_form",
    "app_click_at", "app_close",
}
DESKTOP_DESTRUCTIVE = {
    "app_action", "app_find_and_act", "app_fill_form", "app_click_at", "app_close",
}
DESKTOP_NON_IDEMPOTENT = {
    "app_launch", "app_action", "app_find_and_act", "app_fill_form", "app_click_at", "app_close",
}
