# Achilles QA e QA Studio

O toolset `qa` transforma tráfego observado e contratos OpenAPI em casos HTTP reproduzíveis. A mesma implementação atende CLI, MCP, REST, workflows e a interface local do Studio.

## Início rápido

Por segurança, o escopo inicial aceita somente `localhost`, `127.0.0.1` e `::1` e métodos `GET`, `HEAD` e `OPTIONS`.

```powershell
achilles qa discover --openapi http://127.0.0.1:8000/openapi.json
achilles qa request http://127.0.0.1:8000/health --expect-status 200
achilles qa run examples/qa-smoke.yaml
achilles qa report --format html
achilles studio
```

O Studio abre em `http://127.0.0.1:8766`. Ele usa um token efêmero no documento, exige um header não simples nas chamadas da interface, restringe origem e conexão ao loopback e não habilita CORS.

## Política de escopo

Edite `%LOCALAPPDATA%\Achilles\policy.yaml` no Windows:

```yaml
qa:
  allow_hosts:
    - localhost
    - 127.0.0.1
    - api.staging.example.com
  deny_hosts:
    - production.example.com
  allow_private_networks: false
  allow_mutating_methods: false
```

Para testar `POST`, `PUT`, `PATCH` ou `DELETE`, duas condições são obrigatórias:

1. `qa.allow_mutating_methods: true` na política local;
2. `allow_mutating: true` no caso de teste.

Isso impede que uma suíte gerada por descoberta execute mutações silenciosamente. O gerador `qa_plan` omite endpoints mutáveis por padrão e os devolve na lista `skipped` para revisão.

## Formato da suíte

```yaml
name: smoke-staging
base_url: https://api.staging.example.com
concurrency: 4
stop_on_failure: false
variables:
  API_TOKEN: ${API_TOKEN}
cases:
  - id: health
    name: Health responde rapidamente
    method: GET
    path: /health
    expected_status: [200]
    assertions:
      - kind: json_path_equals
        key: status
        expected: ok
      - kind: response_time_ms
        expected: 1500
  - id: create-test-record
    name: Cria registro descartável
    method: POST
    path: /test-records
    headers:
      Authorization: Bearer ${API_TOKEN}
    json_body:
      name: Achilles fixture
    expected_status: [201]
    allow_mutating: true
```

Variáveis podem ser fornecidas na suíte ou pelo ambiente como `ACHILLES_QA_VAR_API_TOKEN`. Evidências e relatórios passam pela redação de segredos do Achilles.

## Assertions

- `status`: status presente na lista esperada;
- `header_exists`: header existe;
- `header_equals`: header tem o valor esperado;
- `body_contains`: texto existe no corpo;
- `json_path_equals`: caminho simples como `data.user.id` tem o valor esperado;
- `response_time_ms`: duração abaixo do limite;
- `schema_required`: objeto JSON possui todas as chaves informadas.

## Relatórios e CI

Cada suíte gera um `run_id` e grava o relatório sob o diretório de dados do Achilles. `qa_report` exporta JSON, HTML standalone ou JUnit XML. O JUnit pode ser publicado por GitHub Actions, GitLab CI, Jenkins e outras ferramentas de CI.

## Auditoria defensiva

`qa_security_audit` verifica evidências como CSP, HSTS, CORS wildcard, `nosniff`, cookies sem `Secure` e exposição do header `Server`. Ele não tenta explorar autorização, injeção, banco de dados ou gerar carga. Esses itens aparecem explicitamente em `not_tested`.

## Limites

- Descoberta não inventa valores válidos para parâmetros OpenAPI.
- Endpoints com placeholders precisam de revisão ou variáveis.
- O runner não substitui testes de carga especializados.
- A autorização para testar o alvo continua sendo responsabilidade de quem opera o Achilles.
- O Studio é local e não deve ser publicado atrás de proxy ou exposto na rede.
