"""Prepare the browser bookmark extension for manual installation."""

import base64
import ctypes
import os
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Tuple

ASSETS = ("manifest.json", "bridge.html")
PACKAGE_NAME = "Achilles Browser Bridge"


def desktop_dir() -> Path:
    """Return the user's Desktop, including Windows folder redirection."""
    if sys.platform == "win32":
        buffer = ctypes.create_unicode_buffer(32768)
        result = ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buffer)
        if result == 0 and buffer.value:
            return Path(buffer.value)
    return Path.home() / "Desktop"


def prepare_extension(desktop: Path) -> Tuple[Path, Path]:
    """Write the unpacked folder Chrome needs and a portable ZIP alongside it."""
    source = Path(__file__).resolve().parents[1] / "browser_extension"
    files = {name: (source / name).read_bytes() for name in ASSETS}
    if not desktop.is_dir():
        raise FileNotFoundError(f"Área de Trabalho não encontrada: {desktop}")
    folder = desktop / PACKAGE_NAME
    folder.mkdir(exist_ok=True)
    for name, contents in files.items():
        destination = folder / name
        if not destination.is_file() or destination.read_bytes() != contents:
            destination.write_bytes(contents)
    archive = desktop / (PACKAGE_NAME + ".zip")
    temporary = desktop / ("." + PACKAGE_NAME + f".{os.getpid()}.zip")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for name, contents in files.items():
                bundle.writestr(name, contents)
        os.replace(temporary, archive)
    finally:
        temporary.unlink(missing_ok=True)
    return folder, archive


def show_toast() -> bool:
    """Best-effort Windows toast; terminal instructions remain available."""
    if sys.platform != "win32":
        return False
    script = r"""
try {
  [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
  [Windows.UI.Notifications.ToastNotification, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
  $xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
  $nodes = $xml.GetElementsByTagName('text')
  $nodes.Item(0).AppendChild($xml.CreateTextNode('Extensão do Achilles pronta')) > $null
  $nodes.Item(1).AppendChild($xml.CreateTextNode('Na Área de Trabalho, use a pasta Achilles Browser Bridge em chrome://extensions > Carregar sem compactação.')) > $null
  $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
  [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Microsoft.Windows.PowerShell').Show($toast)
} catch { exit 1 }
"""
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=8,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def run_extension_package() -> None:
    try:
        folder, archive = prepare_extension(desktop_dir())
    except OSError as exc:
        print(f"Erro ao preparar a extensão: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    show_toast()
    print(f"ZIP criado: {archive}")
    print(f"Pasta para instalar: {folder}")
    print("1. Abra o Chrome ou Edge no mesmo perfil que o Achilles usa.")
    print("2. Acesse chrome://extensions (ou edge://extensions) e ative o Modo do desenvolvedor.")
    print("3. Clique em 'Carregar sem compactação' e selecione a pasta acima, não o ZIP.")
    print("4. Confirme o ID iaheffblcnihpbdecmnkioimgdjjffgo.")
