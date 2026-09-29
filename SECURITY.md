# Política de segurança

O Achilles controla sessões de navegador e pode observar páginas autenticadas. Trate o perfil CDP, os resultados das ferramentas e os relatórios exportados como dados potencialmente sensíveis.

## Reportar uma vulnerabilidade

Use [GitHub Security Advisories](https://github.com/PedroReoli/Achilles-CDP-Agent/security/advisories/new) para enviar o relato de forma privada ou escreva para `security@reoli.org`. Evite issues públicas com tokens, cookies, URLs privadas ou passos que exponham uma sessão real. Inclua versão, sistema operacional, passos reproduzíveis em perfil descartável e impacto observado. O mantenedor avaliará o relato antes de uma divulgação pública.

## Limites de confiança

- **CDP:** o endpoint de depuração dá amplo controle sobre o perfil conectado. Mantenha-o em `127.0.0.1`, use um perfil dedicado e não exponha a porta à rede. Acesso local à máquina também deve ser tratado como sensível.
- **REST:** `achilles start` escuta em `127.0.0.1`, exige Bearer token e valida peer, Host e Origin. `ACHILLES_API_TOKEN` pode definir o token; sem ele, um token aleatório é mostrado no stderr ao iniciar. Não compartilhe o token.
- **MCP:** `achilles mcp` comunica-se por stdio com o processo cliente. Ele não abre listener HTTP nem aplica o Bearer token do REST. Configure apenas clientes MCP confiáveis.
- **Favoritos:** a extensão `Achilles Browser Bridge` pede permissão de leitura e escrita dos favoritos do perfil em que for instalada. Ela não recebe mensagens de sites. Instale-a somente no perfil que deseja controlar.
- **Redação:** URLs, tráfego e relatórios passam por regras para segredos conhecidos. Esse filtro é de melhor esforço e não garante remoção de todo dado confidencial, especialmente conteúdo arbitrário de páginas. Revise resultados antes de compartilhá-los.
- **Navegação:** a ferramenta de navegação aceita `http`, `https` e `about`; o navegador ainda pode alcançar outros conteúdos por interações na página. A auditoria de segurança é passiva e não substitui uma avaliação completa.

Testes de integração usam perfis temporários e servidores locais. Não execute testes ou exemplos de automação mutável em um perfil pessoal sem revisar os comandos.
