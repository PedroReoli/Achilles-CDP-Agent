# Roadmap

## Entregue na linha 2.2

- Sessões nomeadas com porta e perfil isolados.
- `doctor --json` e `doctor --fix` para automação e reparo do PATH.
- Ações semânticas, recuperação de referências, formulários, downloads, uploads e diálogos.
- Eventos incrementais e SSE na API local.
- Extração paginada/infinite scroll com deduplicação e limites.
- Workflows JSON/YAML com checkpoints, retomada, CSV/JSON/JSONL e Mission Runner.
- Políticas locais de ferramenta, modo read-only e allow/deny de domínios.
- Benchmark reproduzível publicado como artefato do CI.
- Runtime Windows UI Automation em processo isolado para abrir, observar e controlar aplicativos.
- Fallback visual com screenshot recente, ações relativas e proteção contra estado obsoleto.
- Política desktop por aplicativo/janela e bloqueio de superfícies de credenciais e logon.
- Runtime QA com descoberta OpenAPI/tráfego, casos HTTP, assertions e suítes reproduzíveis.
- Auditoria defensiva de endpoints, relatórios JSON/HTML/JUnit e QA Studio local.
- Toolset MCP `qa` e operações QA no Mission Runner.

## Próximo

- OCR local opcional para enriquecer interfaces sem árvore de acessibilidade.
- Adaptadores oficiais de configuração para mais clientes MCP.
- Dashboard histórico de benchmark entre releases.
- Baseline visual e comparação de screenshots entre releases.
- Testes de acessibilidade e geração assistida de dados por schema OpenAPI.

## Limites

Achilles detecta CAPTCHA, WAF e 2FA e transfere o controle para uma pessoa. Evasão desses controles não faz parte do projeto.

No desktop, UAC, logon, DRM, anti-cheat e processos com privilégio superior não são prometidos como automatizáveis.

O runtime QA exige escopo autorizado, não executa exploração destrutiva e não substitui ferramentas dedicadas de carga ou pentest.
