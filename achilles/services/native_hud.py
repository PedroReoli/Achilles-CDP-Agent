"""
Native Title Bar HUD Overlay para Windows (fora da guia / sem injeção no HTML).
Flutua diretamente na barra de título do Google Chrome, ao lado dos botões de controle de janela.
"""

import ctypes
import logging
import queue
import sys
import threading
from ctypes import wintypes
from typing import Optional

LOG = logging.getLogger(__name__)


class NativeHudOverlay:
    """Overlay nativo do Windows que se ancora na barra de título do Chrome."""

    _instance: Optional["NativeHudOverlay"] = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls, cdp_port: int = 9222) -> "NativeHudOverlay":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(cdp_port)
            return cls._instance

    def __init__(self, cdp_port: int = 9222) -> None:
        self.cdp_port = cdp_port
        self.enabled = sys.platform == "win32"
        self._thread: Optional[threading.Thread] = None
        self._queue: queue.Queue = queue.Queue()
        self._running = False
        self._chrome_hwnd: Optional[int] = None
        self._chrome_pid: Optional[int] = None
        self._user32 = ctypes.windll.user32 if self.enabled else None

        if self.enabled:
            self._start()

    def _start(self) -> None:
        if self._running or not self.enabled:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_gui, daemon=True, name="AchillesNativeHudThread")
        self._thread.start()

    def update(self, status: str = "idle", message: str = "") -> None:
        """Envia atualização de status/mensagem para o HUD nativo."""
        if not self.enabled:
            return
        self._queue.put({"action": "update", "status": status, "message": message})

    def close(self) -> None:
        """Encerra o HUD nativo."""
        if not self._running:
            return
        self._running = False
        self._queue.put({"action": "close"})

    def _get_chrome_pid(self) -> Optional[int]:
        """Obtém o PID do processo Chrome escutando na porta CDP."""
        try:
            import subprocess
            cmd = f"Get-NetTCPConnection -LocalPort {self.cdp_port} -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess"
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", cmd],
                timeout=2,
                stderr=subprocess.DEVNULL,
            ).decode().strip()
            if out:
                return int(out.split()[0])
        except Exception:
            pass
        return None

    def _find_chrome_hwnd(self, hdesk: int) -> Optional[int]:
        """Localiza a janela principal do Chrome (Chrome_WidgetWin_1) pelo PID."""
        if not self._chrome_pid:
            self._chrome_pid = self._get_chrome_pid()
        if not self._chrome_pid or not self._user32:
            return None

        found_hwnd = None
        def enum_cb(hwnd, lparam):
            nonlocal found_hwnd
            if self._user32.IsWindowVisible(hwnd):
                pid = wintypes.DWORD()
                self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value == self._chrome_pid:
                    cname = ctypes.create_unicode_buffer(256)
                    self._user32.GetClassNameW(hwnd, cname, 256)
                    if cname.value == "Chrome_WidgetWin_1":
                        rect = wintypes.RECT()
                        self._user32.GetWindowRect(hwnd, ctypes.byref(rect))
                        # Ignora janelas pequenas/tooltips
                        if (rect.right - rect.left) > 350 and (rect.bottom - rect.top) > 200:
                            found_hwnd = hwnd
                            return False
            return True

        wnd_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(enum_cb)
        self._user32.EnumDesktopWindows(hdesk, wnd_proc, 0)
        return found_hwnd

    def _run_gui(self) -> None:
        try:
            import tkinter as tk
        except ImportError:
            LOG.debug("Tkinter não disponível para HUD nativo.")
            return

        # Garante que a thread acessa o desktop interativo do usuário no Windows
        hdesk = self._user32.OpenDesktopW("Default", 0, False, 0x01FF)
        if hdesk:
            self._user32.SetThreadDesktop(hdesk)

        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", 0.95)

        BG_TRANSPARENT = "#000001"
        root.configure(bg=BG_TRANSPARENT)
        try:
            root.attributes("-transparentcolor", BG_TRANSPARENT)
        except Exception:
            pass

        pill_w = 210
        pill_h = 28
        is_collapsed = False

        canvas = tk.Canvas(root, width=pill_w, height=pill_h, bg=BG_TRANSPARENT, highlightthickness=0)
        canvas.pack(fill="both", expand=True)

        def round_rect(x1, y1, x2, y2, r=12, **kwargs):
            points = (
                x1 + r, y1,
                x2 - r, y1,
                x2, y1,
                x2, y1 + r,
                x2, y2 - r,
                x2, y2,
                x2 - r, y2,
                x1 + r, y2,
                x1, y2,
                x1, y2 - r,
                x1, y1 + r,
                x1, y1,
            )
            return canvas.create_polygon(points, **kwargs, smooth=True)

        # Fundo e borda arredondada estilo dark/purple
        bg_poly = round_rect(1, 1, pill_w - 1, pill_h - 1, r=13, fill="#0f172a", outline="#a855f7", width=1)
        dot = canvas.create_oval(9, 10, 17, 18, fill="#22c55e", outline="#4ade80", width=1)
        canvas.create_text(24, 14, text="ACHILLES", fill="#c084fc", font=("Segoe UI", 8, "bold"), anchor="w")
        label_text = canvas.create_text(80, 14, text="Achilles ativo", fill="#f1f5f9", font=("Segoe UI", 8), anchor="w")
        btn_min = canvas.create_text(pill_w - 12, 13, text="_", fill="#94a3b8", font=("Segoe UI", 8, "bold"), anchor="center")

        def toggle_collapse(event=None):
            nonlocal is_collapsed, pill_w, bg_poly
            is_collapsed = not is_collapsed
            if is_collapsed:
                pill_w = 105
                canvas.itemconfig(label_text, state="hidden")
                canvas.itemconfig(btn_min, text="+")
                canvas.coords(btn_min, pill_w - 10, 14)
            else:
                pill_w = 210
                canvas.itemconfig(label_text, state="normal")
                canvas.itemconfig(btn_min, text="_")
                canvas.coords(btn_min, pill_w - 12, 13)
            canvas.delete(bg_poly)
            bg_poly = round_rect(1, 1, pill_w - 1, pill_h - 1, r=13, fill="#0f172a", outline="#a855f7", width=1)
            canvas.tag_lower(bg_poly)

        canvas.tag_bind(btn_min, "<Button-1>", toggle_collapse)

        # Evita roubar foco da janela do Chrome ao ser clicado (WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
        root.update_idletasks()
        try:
            tk_hwnd = self._user32.GetParent(root.winfo_id()) or root.winfo_id()
            style = self._user32.GetWindowLongW(tk_hwnd, -20)
            self._user32.SetWindowLongW(tk_hwnd, -20, style | 0x08000000 | 0x00000080)
        except Exception:
            pass

        # Configuração de status
        status_colors = {
            "idle": ("#22c55e", "#4ade80"),
            "acting": ("#c084fc", "#e9d5ff"),
            "waiting_human": ("#f59e0b", "#fde68a"),
        }

        last_x, last_y = -9999, -9999
        is_visible = True

        def poll_sync():
            nonlocal last_x, last_y, is_visible

            # Processa mensagens na fila
            while not self._queue.empty():
                try:
                    item = self._queue.get_nowait()
                    if item.get("action") == "close":
                        root.destroy()
                        return
                    if item.get("action") == "update":
                        st = item.get("status", "idle")
                        msg = item.get("message", "")
                        fill_c, out_c = status_colors.get(st, ("#22c55e", "#4ade80"))
                        canvas.itemconfig(dot, fill=fill_c, outline=out_c)
                        if msg:
                            display_msg = msg[:20] + "..." if len(msg) > 20 else msg
                            canvas.itemconfig(label_text, text=display_msg)
                except Exception:
                    break

            # Localiza ou revalida a janela do Chrome
            if not self._chrome_hwnd or not self._user32.IsWindow(self._chrome_hwnd):
                self._chrome_hwnd = self._find_chrome_hwnd(hdesk)

            if not self._chrome_hwnd or not self._user32.IsWindow(self._chrome_hwnd):
                if is_visible:
                    root.withdraw()
                    is_visible = False
                root.after(80, poll_sync)
                return

            # Se o Chrome estiver minimizado, oculta o pill
            if self._user32.IsIconic(self._chrome_hwnd):
                if is_visible:
                    root.withdraw()
                    is_visible = False
                root.after(80, poll_sync)
                return

            # Verifica se o Chrome ou janelas do seu processo estão em primeiro plano
            fg = self._user32.GetForegroundWindow()
            fg_pid = wintypes.DWORD()
            self._user32.GetWindowThreadProcessId(fg, ctypes.byref(fg_pid))
            is_chrome_active = (fg_pid.value == self._chrome_pid or fg == tk_hwnd)

            if not is_chrome_active:
                if is_visible:
                    root.withdraw()
                    is_visible = False
                root.after(80, poll_sync)
                return

            if not is_visible:
                root.deiconify()
                is_visible = True

            # Obtém coordenadas e posiciona na barra de título ao lado do minimizar
            rect = wintypes.RECT()
            self._user32.GetWindowRect(self._chrome_hwnd, ctypes.byref(rect))
            is_max = self._user32.IsZoomed(self._chrome_hwnd)

            right_offset = 145  # Largura dos 3 botões nativos do Windows (minimizar/maximizar/fechar)
            target_x = rect.right - right_offset - pill_w - 8
            target_y = (rect.top + 8) if is_max else (rect.top + 5)

            if target_x != last_x or target_y != last_y:
                root.geometry(f"{pill_w}x{pill_h}+{target_x}+{target_y}")
                last_x, last_y = target_x, target_y

            root.after(45, poll_sync)

        root.after(20, poll_sync)
        root.mainloop()
