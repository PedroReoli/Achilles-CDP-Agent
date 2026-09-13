# Achilles CDP Agent

Framework Python 3.9+ que conecta agentes de IA a Chrome/Chromium via CDP. REST e MCP usam os mesmos Application Services: sessão, captura de rede, snapshots, ações e auditoria passiva.

## Executar

```powershell
python -m pip install -e ".[test]"
python -m achilles start --cdp-port 9222 --port 8765
python -m achilles mcp --cdp-port 9222
```

O Chrome deve estar iniciado com depuração remota e perfil próprio. O modo attach preserva o navegador ao encerrar o Achilles.

REST escuta somente em `127.0.0.1` e exige Bearer token. Configure `ACHILLES_API_TOKEN` ou utilize o token gerado no stderr ao iniciar. A opção `--cdp-port` também está disponível no MCP.

## API e MCP

O catálogo está em `GET /api/tools.json` e MCP `tools/list`. Execute uma operação via `POST /api/tools/{name}` ou MCP `tools/call`.

- `browser_status`, `browser_list_pages`, `browser_select_page`
- `browser_snapshot`, `browser_action`
- `network_query`, `network_curl`, `network_postman`
- `security_audit`

Snapshots retornam `snapshot_id`, `page_id` e `element_ref`. Ações exigem essas referências e usam Locators nativos, com detecção de referências obsoletas. Headers de resposta alimentam a auditoria; exports de rede possuem redação de credenciais.

```json
{
  "mcpServers": {
    "achilles": {
      "command": "achilles",
      "args": ["mcp", "--cdp-port", "9222"]
    }
  }
}
```

## Testes

```powershell
python -m unittest discover tests -v
python -m playwright install chromium
$env:ACHILLES_BROWSER_TESTS = '1'
python -m unittest discover tests -v
```

Os testes de browser usam Chromium descartável e um servidor de fixtures local.

## Documentação

[Arquitetura, contratos, limites e migração da v1](.docs/application-services.md).

A versão 2 altera os contratos de IDs e ferramentas. Recursos legados fora do novo catálogo não são expostos pelos transportes. Consulte o guia de migração antes de atualizar clientes existentes.

O executável existente em `dist` é anterior à refatoração. O startup abaixo de 300 ms foi medido para a CLI Python; não representa uma medição do binário onefile.

Licença MIT. Pedro Lucas Reis / Reoli Open Source.
