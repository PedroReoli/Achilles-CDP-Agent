"""Sistema de Internacionalização (i18n) do Achilles CDP Agent (PT-BR e EN)."""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

CONFIG_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Achilles"
CONFIG_FILE = CONFIG_DIR / "config.json"


def get_stored_language() -> str:
    try:
        if CONFIG_FILE.exists():
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            lang = data.get("language", "").lower()
            if lang in ("en", "pt", "pt_br", "pt-br"):
                return "pt" if "pt" in lang else "en"
    except Exception:
        pass
    # Padrão: Português (Brasil)
    return "pt"


def set_stored_language(lang: str) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = {}
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        data["language"] = "pt" if "pt" in lang.lower() else "en"
        CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


STRINGS: Dict[str, Dict[str, str]] = {
    "pt": {
        "banner_subtitle": "ACHILLES CDP AGENT • Automação e Segurança de Navegador • Achilles v2.1",
        "connecting": "Conectando ao Chrome CDP na porta",
        "connected": "Conectado ao Chrome com sucesso!",
        "type_help": "Digite [bold #c084fc]/help[/] para comandos ou [bold #c084fc]/exit[/] para sair.",
        "chrome_not_detected": "Chrome CDP não detectado na porta",
        "starting_persistent_chrome": "Iniciando Google Chrome com perfil persistente em",
        "persistent_profile_info": "Sessões e logins anteriores serão mantidos automaticamente!",
        "lang_switched": "Idioma alterado para Português (Brasil).",
        "help_title": "Catálogo de Comandos do Achilles",
        "cat_nav": "Navegação",
        "cat_inspect": "Inspeção",
        "cat_action": "Ação",
        "cat_network": "Rede & API",
        "cat_security": "Segurança",
        "cat_system": "Sistema",
        "col_category": "Categoria",
        "col_command": "Comando",
        "col_description": "Descrição",
        "col_example": "Exemplo de Uso",
        "desc_open": "Navega a aba atual para a URL especificada",
        "desc_pages": "Lista todas as abas e janelas abertas",
        "desc_select": "Foca e ativa uma aba específica",
        "desc_scroll": "Rola a página (down, up, top, bottom ou pixels) para lazy-load",
        "desc_snap": "Captura árvore semântica com referências [ref]",
        "desc_fill": "Preenche campo de texto usando o [ref]",
        "desc_click": "Clica em um botão, link ou elemento",
        "desc_traffic": "Lista histórico de requisições HTTP",
        "desc_curl": "Exporta cURL seguro com segredos redigidos",
        "desc_read": "Lê o conteúdo da página em Markdown limpo (Reader Mode, ~95% economia de tokens)",
        "desc_report": "Exibe relatório de economia de tokens e rotas de API da sessão",
        "desc_new": "Abre uma nova aba no Chrome (opcional: URL)",
        "desc_close": "Fecha aba ativa ou especificada",
        "desc_ai": "Exibe o protocolo autônomo para agentes de IA",
        "desc_audit": "Auditoria de postura OWASP e cabeçalhos reais",
        "desc_lang": "Alterna idioma do console (pt ou en)",
        "desc_status": "Exibe métricas da sessão e porta CDP",
        "desc_clear": "Limpa a tela do console",
        "desc_exit": "Encerra a sessão interativa com segurança",
        "no_pages": "Nenhuma aba aberta detectada no momento.",
        "open_tabs_title": "Abas Abertas no Navegador",
        "active_badge": "● ATIVA",
        "inactive_badge": "INATIVA",
        "snap_title": "Snapshot Semântico",
        "snap_elements_count": "elementos interativos",
        "col_ref": "Referência [ref]",
        "col_role": "Tipo / Role",
        "col_name": "Nome / Label do Elemento",
        "col_state": "Estado",
        "state_enabled": "Interativo",
        "state_disabled": "Desabilitado",
        "traffic_title": "Histórico de Tráfego de Rede",
        "traffic_empty": "Nenhuma requisição registrada no TrafficJournal até o momento.",
        "col_req_id": "Req ID",
        "col_method": "Método",
        "col_status": "Status",
        "col_url": "URL",
        "col_time": "Tempo",
        "audit_title": "🛡️ Relatório de Auditoria OWASP",
        "security_score": "Score de Segurança",
        "analyzed_url": "URL Analisada",
        "total_findings": "Total de Achados",
        "score_excellent": "EXCELENTE",
        "score_warning": "ATENÇÃO",
        "score_critical": "CRÍTICO",
        "col_severity": "Severidade",
        "col_vulnerability": "Vulnerabilidade / Achado",
        "col_desc_rem": "Descrição & Recomendação",
        "remediation_label": "Correção",
        "navigating_to": "Navegando para",
        "nav_success": "Navegação concluída com sucesso em",
        "scroll_success": "Página rolada com sucesso ({direction})!",
        "tab_selected": "Aba selecionada e trazida para frente!",
        "click_success": "Clique executado com sucesso em",
        "fill_success": "Campo preenchido com",
        "curl_title": "cURL Export (PowerShell)",
        "cmd_not_recognized": "Comando não reconhecido",
        "goodbye": "Achilles encerrado com sucesso. Até logo!",
    },
    "en": {
        "banner_subtitle": "ACHILLES CDP AGENT • Autonomous Browser Automation & Security • Achilles v2.1",
        "connecting": "Connecting to Chrome CDP on port",
        "connected": "Connected to Chrome successfully!",
        "type_help": "Type [bold #c084fc]/help[/] for commands or [bold #c084fc]/exit[/] to quit.",
        "chrome_not_detected": "Chrome CDP not detected on port",
        "starting_persistent_chrome": "Starting Google Chrome with persistent profile at",
        "persistent_profile_info": "Previous logins and sessions will be preserved automatically!",
        "lang_switched": "Language switched to English.",
        "help_title": "Achilles Command Catalog",
        "cat_nav": "Navigation",
        "cat_inspect": "Inspection",
        "cat_action": "Action",
        "cat_network": "Network & API",
        "cat_security": "Security",
        "cat_system": "System",
        "col_category": "Category",
        "col_command": "Command",
        "col_description": "Description",
        "col_example": "Example Usage",
        "desc_open": "Navigates current tab to specified URL",
        "desc_pages": "Lists all open browser tabs and windows",
        "desc_select": "Focuses and activates a specific tab",
        "desc_scroll": "Scrolls page (down, up, top, bottom or pixels) for lazy-loading",
        "desc_snap": "Captures semantic accessibility tree with [ref]",
        "desc_fill": "Fills text input using the [ref]",
        "desc_click": "Clicks a button, link or element",
        "desc_traffic": "Lists captured HTTP requests history",
        "desc_curl": "Exports sanitized cURL command",
        "desc_read": "Reads main page content in clean Markdown (Reader Mode, ~95% token savings)",
        "desc_report": "Displays session token savings and analyzed API routes report",
        "desc_new": "Opens a new tab in Chrome (optional: URL)",
        "desc_close": "Closes active or specified tab",
        "desc_ai": "Displays autonomous protocol instructions for AI agents",
        "desc_audit": "OWASP security posture and real response headers audit",
        "desc_lang": "Switches console language (en or pt)",
        "desc_status": "Shows CDP session metrics and port",
        "desc_clear": "Clears console screen",
        "desc_exit": "Safely exits interactive session",
        "no_pages": "No open browser tabs detected at this moment.",
        "open_tabs_title": "Open Browser Tabs",
        "active_badge": "● ACTIVE",
        "inactive_badge": "INACTIVE",
        "snap_title": "Semantic Snapshot",
        "snap_elements_count": "interactive elements",
        "col_ref": "Reference [ref]",
        "col_role": "Type / Role",
        "col_name": "Element Name / Label",
        "col_state": "State",
        "state_enabled": "Interactive",
        "state_disabled": "Disabled",
        "traffic_title": "Network Traffic History",
        "traffic_empty": "No requests recorded in TrafficJournal so far.",
        "col_req_id": "Req ID",
        "col_method": "Method",
        "col_status": "Status",
        "col_url": "URL",
        "col_time": "Time",
        "audit_title": "🛡️ OWASP Security Audit Report",
        "security_score": "Security Score",
        "analyzed_url": "Analyzed URL",
        "total_findings": "Total Findings",
        "score_excellent": "EXCELLENT",
        "score_warning": "WARNING",
        "score_critical": "CRITICAL",
        "col_severity": "Severity",
        "col_vulnerability": "Vulnerability / Finding",
        "col_desc_rem": "Description & Recommendation",
        "remediation_label": "Remediation",
        "navigating_to": "Navigating to",
        "nav_success": "Navigation successfully completed to",
        "scroll_success": "Page scrolled successfully ({direction})!",
        "tab_selected": "Tab selected and brought to front!",
        "click_success": "Click successfully executed on",
        "fill_success": "Field filled with",
        "curl_title": "cURL Export (PowerShell)",
        "cmd_not_recognized": "Unrecognized command",
        "goodbye": "Achilles closed successfully. See you soon!",
    },
}


class I18n:
    def __init__(self, lang: Optional[str] = None) -> None:
        self.lang = lang or get_stored_language()
        if self.lang not in STRINGS:
            self.lang = "pt"

    def set_lang(self, lang: str) -> None:
        clean = "pt" if "pt" in lang.lower() else "en"
        self.lang = clean
        set_stored_language(clean)

    def t(self, key: str, **kwargs: Any) -> str:
        text = STRINGS.get(self.lang, STRINGS["pt"]).get(key, key)
        if kwargs:
            try:
                return text.format(**kwargs)
            except Exception:
                return text
        return text
