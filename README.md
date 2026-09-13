# 🛡️⚡ Achilles CDP Agent

> **Autonomous Agentic Chrome DevTools Protocol (CDP) Bridge & Security/API Engine**  
> *Open Source • 100% AI-Friendly • Native Model Context Protocol (MCP) • Standalone Windows Executable*

---

## 🏛️ Visão Geral

O **Achilles CDP Agent** é um framework e agente autônomo em Python construído para conectar Inteligências Artificiais (Claude, Cursor, Antigravity, Ollama, GPT-4) diretamente a instâncias reais de navegadores Chromium/Chrome via **Chrome DevTools Protocol (porta `9222`)**.

O sistema foi arquitetado para transformar qualquer navegador em uma **API conversável para IAs**, com recursos avançados de:
1. **Árvore Semântica de Acessibilidade** (IDs numéricos indexados que reduzem o consumo de tokens em até 95%).
2. **Auditoria Profunda de Segurança & Vulnerabilidades** (OWASP Top 10, OWASP API Security, Supabase RLS bypass detection, vazamento de secrets e integridade de banco de dados).
3. **Engenharia Reversa Automática de APIs** (Geração dinâmica de OpenAPI 3.0.0 e Swagger UI interativo a partir do tráfego de rede).
4. **Exportação Determinística de Testes E2E** (Scripts prontos em Playwright para CI/CD).
5. **Visual Overlay no Navegador** (Badges visuais `[#1]`, `[#2]` injetados na tela em tempo real).
6. **Servidor Nativo MCP (Model Context Protocol)** para integração direta com Claude Desktop e Cursor.

---

## 🚀 Instalação & Execução

### Opção 1: Executável Standalone para Windows (.exe)
Baixe o arquivo `achilles.exe` na aba de [Releases](https://github.com/PedroReoli/achilles-cdp) e execute no terminal:

```bash
# Inicia a interface interativa no terminal e o servidor AI Bridge
achilles.exe start --port 8765 --cdp-port 9222
```

### Opção 2: Via Python / Git (Desenvolvimento)
```bash
# Clone o repositório
git clone https://github.com/PedroReoli/achilles-cdp.git
cd "Achilles CDP Agent"

# Instale as dependências
pip install -r requirements.txt

# Inicie a CLI
python -m achilles start
```

---

## 🖥️ Interface de Terminal (TUI)

O Achilles vem com uma interface rica no terminal baseada no `Rich` e `Typer`:

```text
   ___         __     _  __ __               _____   ___     ___                    __ 
  / _ | ____  / /    (_)/ // / ___  ___     / ___/  / _ \   / _ \  ___ _ ___  ___  / /_
 / __ |/ __/ / _ \  / // // / / -_)(_-<    / /__   / // /  / ___/ / _ `// -_)/ _ \/ __/
/_/ |_|\__/ /_//_/ /_//_//_/  \__//___/    \___/  /____/  /_/     \_, / \__/ /_//_/\__/ 
                                                                 /___/                  
```

### Subcomandos da CLI:
* `achilles start` — Sobe o servidor REST AI Bridge, Swagger reverso e monitor de tráfego.
* `achilles mcp` — Inicia o servidor MCP via `stdio` para agentes de IA.

---

## 🔌 Configuração do Servidor MCP (Claude Desktop & Cursor)

Para conectar o Achilles diretamente ao **Claude Desktop**, adicione ao seu arquivo `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "achilles-cdp": {
      "command": "achilles",
      "args": ["mcp"]
    }
  }
}
```

### Ferramentas Expostas para a IA:
* `achilles_get_dom_tree`: Retorna a árvore semântica compacta com IDs numéricos para a IA entender e decidir a próxima ação.
* `achilles_click_id`: Executa cliques por ID numérico (`id: 1`).
* `achilles_fill_id`: Preenche inputs por ID numérico (`id: 2, value: "texto"`).
* `achilles_security_audit`: Executa auditoria instantânea de segurança na página ativa.

---

## 🛡️ Endpoints da API REST

| Endpoint | Método | Descrição |
| :--- | :--- | :--- |
| `/api/status` | `GET` | Retorna saúde da conexão CDP e métricas da aba ativa. |
| `/api/dom/tree` | `GET` | Árvore de acessibilidade semântica com IDs indexados. |
| `/api/dom/highlight` | `POST` | Injeta badges flutuantes `[#1]`, `[#2]` no Chrome real. |
| `/api/dom/clear-highlight` | `POST` | Remove os badges visuais da tela. |
| `/api/routes/openapi.json` | `GET` | Especificação OpenAPI 3.0.0 deduzida do tráfego capturado. |
| `/api/routes/swagger` | `GET` | Interface visual do Swagger UI rodando sobre o portal inspecionado. |
| `/api/routes/postman` | `GET` | Exportação de requisições no formato Postman Collection v2.1.0. |
| `/api/security/audit` | `GET` | Diagnóstico de vulnerabilidades OWASP, Supabase RLS e Risk Score (0-100). |
| `/api/export/playwright-test` | `GET` | Gera arquivo `test_flow.py` para testes automatizados. |
| `/api/tools.json` | `GET` | Contratos de Tool Calling para OpenAI, Gemini e Claude. |

---

## 🧪 Testes Automatizados

```bash
# Executa a suíte completa de testes unitários
python -m unittest discover tests -v
```

---

## 📦 Compilação de Novo Executável (.exe)

```bash
python packaging/build_exe.py
```

O binário final é gerado em `dist/achilles.exe`.

---

## 📜 Licença & Governança

Projeto distribuído sob a licença **MIT Permissiva**.  
Governança e padrões de código alinhados ao ecossistema **ReoliCode**.
