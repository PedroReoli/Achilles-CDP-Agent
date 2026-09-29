# Achilles Application Services — versão 2

Os transportes compartilham `ApplicationServices.call(name, arguments)` e os mesmos modelos Pydantic. Uma instância contém sessão, journal, snapshots, executor e auditor. REST e MCP executados em processos separados têm sessões separadas: paridade de comportamento não significa compartilhamento de memória entre processos.

## Instalação e execução

```powershell
python -m pip install -e ".[test]"
python -m achilles start --cdp-port 9333 --port 8765
python -m achilles mcp --cdp-port 9333
```

O Achilles conecta ao Chrome ou Edge pelo Playwright sobre CDP. Se a porta estiver fechada, a primeira operação que precisa do navegador tenta iniciar o executável configurado com perfil persistente próprio, fora do loop stdio. `browser_status` e o handshake MCP não iniciam o navegador. `BrowserSessionManager.close()` encerra o transporte Playwright sem chamar `Browser.close()` ou `BrowserContext.close()`; o navegador iniciado para uso persistente permanece disponível.

`ACHILLES_BROWSER=edge` seleciona o executável e o perfil persistente do Edge para partida automática. Uma porta CDP já aberta prevalece sobre essa seleção. Operações de favoritos usam a extensão `Achilles Browser Bridge` no perfil conectado; consulte [instalação e limites](browser-bookmarks.md).

No REST, configure `ACHILLES_API_TOKEN` no ambiente ou use o token aleatório exibido uma vez no stderr ao iniciar. Todos os endpoints disponíveis exigem `Authorization: Bearer <token>`. O listener da CLI aceita somente `127.0.0.1`, desabilita proxy headers e limita conexões concorrentes. A aplicação verifica peer, Host, Origin e limita corpos a 1 MiB. Tokens devem ser distintos por instalação/processo.

## Contrato compartilhado

`GET /api/tools.json` e MCP `tools/list` retornam o mesmo catálogo. Cada operação REST é `POST /api/tools/{name}`; o corpo é o objeto `arguments` da tool MCP.

| Operação principal | Argumentos |
| --- | --- |
| `browser_status` | `{}` |
| `browser_list_pages` | `{}` |
| `browser_select_page` | `page_id` |
| `browser_snapshot` | `page_id?`, `limit?` (1–1000) |
| `browser_action` | `action`, `page_id`, `snapshot_id`, `element_ref`, `value?`, `timeout_ms?` |
| `browser_bookmarks_list` | `parent_id?`, `limit?` (1–500) |
| `browser_bookmarks_search` | `query`, `limit?` (1–500) |
| `browser_bookmarks_create` | `title`, `url`, `parent_id?` |
| `browser_bookmarks_update` | `id`, `title?`, `url?` |
| `browser_bookmarks_remove` | `id` |
| `network_query` | `page_id?`, `limit?` (1–500) |
| `network_curl` | `request_id`, `shell?` (`posix` ou `powershell`) |
| `network_postman` | `{}` |
| `security_audit` | `page_id?` |

Exemplo de ação, usando os valores reais obtidos no snapshot:

```json
{
  "action": "fill",
  "page_id": "page_...",
  "snapshot_id": "snap_...",
  "element_ref": "frame_.../document_epoch_node",
  "value": "novo valor",
  "timeout_ms": 5000
}
```

`fill` substitui o conteúdo pelo Locator nativo. `click`, `hover`, `press` e `select` também usam Locators; não há clique por coordenadas. Ações são serializadas por página. Nenhuma ação mutável recebe retry automático. `status=executed` indica que a chamada Playwright terminou; a verificação posterior informa se um snapshot pôde ser capturado. Isso não equivale a uma asserção de sucesso de negócio ou ao término de todas as tarefas assíncronas do site.

## Identidade e acessibilidade

Cada documento recebe epoch, WeakMap por nó e um MutationObserver. Os identificadores sobrevivem a reordenações do mesmo nó, mas não à sua substituição, navegação ou geração de conexão diferente. Attributes de instrumentação são ignorados pelo observer. Snapshots expirados geram `STALE_ELEMENT_REF`.

Accessible names, roles e estados são enriquecidos com `DOMSnapshot.captureSnapshot` e `Accessibility.getFullAXTree`. O campo `accessibility` informa se houve fallback DOM, inclusive em frames indisponíveis/OOPIF. Shadow roots abertos e `page.frames` são percorridos. Raízes fechadas e semântica de canvas não estão implementadas. A instrumentação é removida no encerramento normal dos Application Services quando os frames ainda estão acessíveis.

A seleção é explícita ou a última aba descoberta; não há promessa de inferir continuamente qual aba recebeu foco físico do usuário. `browser_select_page` fixa a escolha e traz a aba para frente. Um popup novo torna-se selecionado ao ser descoberto.

## Rede e redação

O journal correlaciona objetos Request e seus Responses, incluindo redirects, timings e falhas. Retém no máximo 500 exchanges; request bodies e response bodies textuais capturados têm limite de 64 KiB. A fila de processamento de eventos tem limite de 128 tarefas e informa `dropped_events`. Existem quatro slots para leitura de bodies.

Para evitar materializar respostas arbitrariamente grandes, bodies sem Content-Length conhecido, comprimidos, binários e streaming são omitidos com `body_state` explícito. Headers/status permanecem disponíveis. A captura começa ao conectar; o histórico anterior do navegador não é recuperado nem provoca reload automático. WebSocket e SSE não são features deste recorte.

Dados brutos necessários à auditoria permanecem apenas no journal em memória até evicção/encerramento. Exports, consultas de rede, URLs, cookies e credenciais reconhecidas são redigidos. cURL exportado contém placeholders e não reproduz uma sessão autenticada sem substituir explicitamente esses valores. PowerShell usa argumentos em aspas simples com duplicação de apóstrofos; a variante é voltada ao PowerShell 7 com passagem moderna de argumentos nativos.

## Auditoria

Somente os response headers de uma navegação capturada alimentam CSP/HSTS/enquadramento. Ausência de captura produz `not_observed`, nunca uma conclusão de ausência de headers. Inspeções de CORS coincidente com credentials são candidatas de baixa confiança; não comprovam reflexão arbitrária. Wildcard com credentials é reportado como combinação inválida, sem alegar bypass do navegador.

JWTs são decodificados, não validados criptograficamente. HS256 isolado não é achado. `alg=none`, ausência de expiração e claims administrativos têm evidência redigida. Claims administrativos não comprovam falha de autorização no servidor. A auditoria é passiva; integridade de banco e exploração de autorização aparecem como `not_tested`. O score usa pesos critical=35, high=20, medium=10, low=3 multiplicados por confiança, limitados a 100.

## MCP e migração

O servidor stdio implementa duas eras de protocolo. A legada usa `initialize`, `notifications/initialized`, `ping`, `tools/list`, `tools/call` e cancelamento nas versões `2024-11-05`, `2025-06-18` e `2025-11-25`. A era `2026-07-28` usa `server/discover` ou chamada direta com versão e capacidades em `params._meta`, sem handshake; as respostas incluem `resultType` e identidade em `_meta`. A seleção de era vale para a conexão stdio, enquanto a versão moderna é conferida em cada requisição. O transporte limita mensagens a 1 MiB e concorrência a 32 requisições. Stdout contém exclusivamente JSON-RPC UTF-8. O servidor MCP é implementado no projeto para preservar Python 3.9 sem acrescentar o SDK MCP como dependência.

Referências: [ciclo de vida legado](https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle) e [descoberta 2026-07-28](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/server/discover.mdx).

Esta é uma mudança de contrato major. IDs inteiros antigos foram substituídos por referências versionadas. As quatro tools MCP antigas dão lugar ao catálogo acima. Os aliases REST `/api/dom/tree`, `/api/security/audit`, `/api/routes/apis`, `/api/routes/postman`, `/api/status` e `/api/action/{action}` delegam ao catálogo novo.

Os módulos antigos de OpenAPI, overlay, scanner e exportação E2E permanecem no código para migração, mas não são chamados pelos novos transportes. As rotas antigas de Swagger reverso, highlight e exportação de testes não fazem parte do catálogo v2 desta implementação. O exportador antigo não deve ser utilizado para replay de requests mutáveis reais. Nenhuma rotina de replay mutável é exposta no transporte novo.

## Verificação reproduzível

```powershell
python -m unittest discover tests -v
python -m playwright install chromium
$env:ACHILLES_BROWSER_TESTS = '1'
python -m unittest discover tests -v
```

Os testes de navegador iniciam Chromium descartável com porta dinâmica e um servidor HTTP local. Exercitam concorrência de conexão, substituição de nó, ação bloqueada, fill/press/select/hover/click, Shadow DOM, frames aninhados, headers reais, body redigido, seleção de abas, preservação de navegador e reconexão após reinício.

O CI executa testes unitários e lint em Python 3.9 a 3.12 no Windows e Linux. Um job separado roda o teste isolado com Chromium nos dois sistemas em Python 3.12. O lint é configurado para sintaxe 3.9. Para medição local de latência e tamanho de payloads, consulte [benchmark.md](benchmark.md).

Dez inicializações `python -m achilles --help` no ambiente 3.11: mediana 96,6 ms, máximo 104,8 ms. Isso mede a CLI Python, não o bootloader do executável PyInstaller. O binário antigo em dist não foi reconstruído por esta refatoração e ainda não incorpora os novos serviços. Compatibilidade Linux/macOS e assinatura de releases não foram homologadas neste trabalho.
