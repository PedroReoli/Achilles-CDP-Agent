# Contribuindo com o Achilles

Obrigado pelo interesse. Antes de enviar uma mudança, confira o [README](README.md), os [contratos dos serviços](.docs/application-services.md) e a [política de segurança](SECURITY.md). Para vulnerabilidades, use o canal privado descrito nessa política.

## Preparar o ambiente

Use Python 3.9+ e um ambiente virtual. No Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m pip install ruff==0.16.9
.\.venv\Scripts\python.exe -m playwright install chromium
```

Em Linux/macOS, troque `python` por `python3` e `.\.venv\Scripts\python.exe` por `./.venv/bin/python`.

## Validar a mudança

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m ruff check achilles tests scripts setup.py
$env:ACHILLES_BROWSER_TESTS = '1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_browser_integration.py -v
```

Os testes de navegador criam perfis descartáveis. O teste de Edge exige `ACHILLES_EDGE_TESTS=1` e o executável instalado, pois versões de marca podem bloquear a carga automática de extensões. O CI executa testes unitários em Python 3.9–3.12 no Windows e Linux e integração com Chromium em Python 3.12. Não use perfis ou sites reais para adicionar testes.

Para mudanças de desempenho, execute `python scripts/benchmark.py --samples 20 --elements 50` e descreva máquina, versões e limites da comparação. O benchmark não é um critério universal de latência.

## Enviar uma contribuição

1. Abra uma issue para mudanças amplas de contrato ou arquitetura; correções pontuais podem seguir direto em pull request.
2. Faça commits [Conventional Commits](https://www.conventionalcommits.org/) curtos e em português, por assunto.
3. Explique o comportamento alterado, a validação executada e as limitações relevantes na descrição do pull request.
4. Atualize `README.md` para entrada e uso, `.docs/` para contratos e arquitetura e `CHANGELOG.md` para mudanças relevantes ao usuário.

CLI, REST e MCP devem delegar a `ApplicationServices`; mantenha o mesmo contrato entre transportes. Preserve Python 3.9+ e trate dados de páginas, URLs e parâmetros como entradas não confiáveis. A redação de segredos é de melhor esforço: teste sem credenciais reais.
