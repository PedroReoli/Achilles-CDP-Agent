# Histórico de mudanças

Este arquivo registra mudanças relevantes ao usuário. O bloco abaixo reúne alterações locais ainda não publicadas como release.

## 2.2.0 — Não lançado

### Adicionado

- CLI estruturado `achilles call`, busca focal `browser_find` e extração declarativa `browser_extract`.
- Toolsets MCP para reduzir o catálogo padrão entregue aos agentes.
- Reparo e validação automática do PATH nos instaladores.

- `achilles --extension` prepara a extensão de favoritos para instalação manual e notifica o usuário no Windows.
- Ferramentas CLI, MCP e REST para listar, buscar, criar, editar e remover favoritos de Chrome/Edge por extensão com permissão `bookmarks`.
- Relatório HTML com timeline de operações, histórico HTTP e desafios observados.
- Benchmark local reproduzível de conexão CDP, snapshot, leitura e ação.
- Testes de integração com perfis descartáveis de Chromium e, quando instalado, Edge.

### Melhorado

- Ações agora verificam o alvo de forma focal e só geram snapshot posterior quando solicitado.
- Fingerprint nativo do navegador substitui valores fabricados de GPU, Canvas e áudio.
- Suporte mínimo atualizado para Python 3.11.

- Compatibilidade do servidor MCP com inicialização legada e descoberta por requisição, incluindo limitação de respostas grandes como JSON válido.
- Caminho rápido de snapshot e partida assíncrona do navegador ao precisar de CDP.
- `achilles doctor` valida dependências e catálogo MCP sem iniciar ou encerrar navegadores.
- CI com Ruff, matriz Python 3.11–3.14 e integração em Windows/Linux.
- Documentação de instalação, limites de segurança, contribuição e empacotamento.
