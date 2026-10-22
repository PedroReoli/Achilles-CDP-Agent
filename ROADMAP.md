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

## Próximo

- Gravação visual de fluxos manuais para gerar workflows.
- Adaptadores oficiais de configuração para mais clientes MCP.
- Dashboard histórico de benchmark entre releases.

## Limites

Achilles detecta CAPTCHA, WAF e 2FA e transfere o controle para uma pessoa. Evasão desses controles não faz parte do projeto.
