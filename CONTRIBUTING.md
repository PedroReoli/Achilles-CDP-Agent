# Guia de Contribuição — Achilles CDP Agent

Obrigado por querer contribuir com o **Achilles CDP Agent**! Este projeto é mantido como software livre sob a licença MIT.

---

## 🛠️ Configuração do Ambiente de Desenvolvimento

1. **Clone o repositório:**
   ```bash
   git clone https://github.com/PedroReoli/Achilles-CDP-Agent.git
   cd Achilles-CDP-Agent
   ```

2. **Crie e ative um ambiente virtual:**
   ```bash
   # Windows (PowerShell)
   python -m venv .venv
   .venv\Scripts\Activate.ps1

   # Linux / macOS
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Instale o pacote com dependências de teste:**
   ```bash
   pip install -e ".[test,build]"
   pip install ruff
   ```

---

## 🧪 Executando os Testes

Execute a suíte completa de testes unitários:
```bash
python -m unittest discover tests -v
```

Para rodar os testes de integração com Chromium local real:
```bash
python -m playwright install chromium
# PowerShell:
$env:ACHILLES_BROWSER_TESTS = '1'
python -m unittest discover tests -v

# Bash:
export ACHILLES_BROWSER_TESTS=1
python3 -m unittest discover tests -v
```

---

## 🎨 Padronização de Código e Linting

Usamos o **Ruff** para formatação e linting estrito:
```bash
ruff check achilles tests
```

---

## 📐 Diretrizes de Arquitetura

- **Application Services como Fonte da Verdade:** Todos os comandos CLI, rotas REST e ferramentas do MCP delegam estritamente para `achilles.services.ApplicationServices`. Não adicione lógica de negócio em transportes (`api/server.py` ou `mcp/server.py`).
- **Zero Secret Leakage:** Todo tráfego HTTP, URLs, títulos de páginas e conteúdos do DOM expostos para o LLM devem passar pela função `redact()` em `achilles/services/redaction.py`.
- **Compatibilidade Python 3.9+:** O projeto deve continuar rodando em Python 3.9 sem requerer bibliotecas incompatíveis.
