# Histórico de mudanças

Este arquivo registra mudanças relevantes ao usuário. O bloco abaixo reúne alterações locais ainda não publicadas como release.

## Não lançado — 2026-09-29

### Adicionado

- Ferramentas CLI, MCP e REST para listar, buscar, criar, editar e remover favoritos de Chrome/Edge por extensão com permissão `bookmarks`.
- Relatório HTML com timeline de operações, histórico HTTP e desafios observados.
- Benchmark local reproduzível de conexão CDP, snapshot, leitura e ação.
- Testes de integração com perfis descartáveis de Chromium e, quando instalado, Edge.

### Melhorado

- Compatibilidade do servidor MCP com inicialização legada e descoberta por requisição, incluindo limitação de respostas grandes como JSON válido.
- Caminho rápido de snapshot e partida assíncrona do navegador ao precisar de CDP.
- `achilles doctor` valida dependências e catálogo MCP sem iniciar ou encerrar navegadores.
- CI com Ruff, matriz Python 3.9–3.12 e integração em Windows/Linux.
- Documentação de instalação, limites de segurança, contribuição e empacotamento.
