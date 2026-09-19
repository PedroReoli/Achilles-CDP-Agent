# Política de Segurança — Achilles CDP Agent

O **Achilles CDP Agent** conecta agentes autônomos de IA e desenvolvedores a sessões ativas do Google Chrome/Chromium via Chrome DevTools Protocol (CDP). Por lidar com credenciais, cookies e sessões de usuários reais em navegação compartilhada, a segurança e a privacidade são pilares inegociáveis.

---

## 🛡️ Nosso Compromisso: Zero Secret Leakage

1. **Redação Recursiva Ativa:** Toda informação trafegada através de requisições (`network_query`), exportações (`network_curl`, `network_postman`) e árvores de observação (`browser_snapshot`) passa por sanitização automática contra mais de 10 classes de segredos (JWT, API keys, tokens de sessão, credenciais bancárias e dados de formulários sensíveis).
2. **Loopback Estrito:** O REST Bridge do Achilles e o servidor MCP stdio foram desenhados para aceitar apenas conexões originadas do loopback local (`127.0.0.1`, `::1`), protegidas por tokens de autenticação Bearer gerados com entropia criptográfica (`secrets.token_urlsafe(32)`).
3. **Bloqueio de Origens Externas e Esquemas Sensíveis:** O acesso cross-origin via browser é explicitamente bloqueado (`BROWSER_ORIGIN_BLOCKED`) e esquemas de arquivos locais (`file://`) ou internos (`chrome://`) são desativados por padrão para prevenir ataques de Local File Disclosure (LFD) ou SSRF induzidos por prompt injection.

---

## 🚨 Como Reportar Vulnerabilidades

Se você identificou uma vulnerabilidade de segurança, **não abra uma issue pública**. 

Por favor, relate o incidente de forma privada:
- **E-mail:** `security@reoli.org` ou diretamente ao mantenedor via [GitHub Security Advisories](https://github.com/PedroReoli/Achilles-CDP-Agent/security/advisories/new).
- Inclua detalhes como:
  - Descrição da vulnerabilidade e passos reproduzíveis (PoC).
  - Versão do Achilles CDP Agent e versão do Python/Chrome utilizada.
  - Impacto potencial no isolamento do navegador ou vazamento de contexto.

Responderemos em até **48 horas úteis** confirmando o recebimento e coordenando a correção e divulgação responsável.

---

## 🔒 Boas Práticas ao Usar o Achilles

- **Perfil Dedicado:** Embora o Achilles suporte perfil persistente para salvar logins em sessões de trabalho, recomendamos utilizar perfis dedicados de automação caso vá executar agentes 100% autônomos sem supervisão humana.
- **Tokens de API:** Nunca versione seu `ACHILLES_API_TOKEN` ou compartilhe sua porta de depuração remota com interfaces expostas à internet (`0.0.0.0`).
