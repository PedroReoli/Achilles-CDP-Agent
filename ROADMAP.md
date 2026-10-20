# Roadmap

## Agora

- Consolidar contratos estruturados para todas as ferramentas MCP.
- Manter instalação global reproduzível em Windows, Linux e macOS.
- Medir regressões de latência e tamanho de resposta no CI.

## Próximo

- Adicionar nomes e descoberta automática à API persistente usada por `achilles call --api-url`.
- Downloads, uploads e espera por eventos de navegador.
- Exportação JSONL/CSV, deduplicação e checkpoints de coleta.
- Plugins de domínio para fluxos autorizados e reproduzíveis.

## Limites

Achilles detecta CAPTCHA, WAF e 2FA e transfere o controle para uma pessoa. Evasão desses controles não faz parte do projeto.
