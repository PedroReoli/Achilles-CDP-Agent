# Runtime de aplicativos Windows

O toolset `desktop` controla janelas da sessão interativa por Windows UI Automation. Ele é incluído no MCP padrão junto de `core` e não requer extensão no aplicativo.

## Fluxo recomendado para agentes

1. Execute `app_list` para descobrir PID, executável e janelas.
2. Use `app_launch` ou `app_attach` para selecionar uma janela.
3. Prefira `app_find_and_act` ou `app_fill_form` para reduzir round-trips.
4. Use `app_snapshot` quando precisar inspecionar a árvore acessível.
5. Se a interface não expuser controles, capture `app_screenshot` e use `app_click_at` imediatamente.
6. Aguarde mudanças com `app_wait_for_state` antes da próxima ação.

Referências de elementos expiram em 60 segundos. Screenshots usados para coordenadas expiram em 30 segundos e são recusados se a janela mudar de posição ou tamanho.

## Exemplos CLI

```powershell
achilles call app_status
achilles call app_list -a '{"limit":20}'
achilles call app_launch -a '{"executable":"notepad.exe"}'
achilles call app_launch -a '{"uri":"ms-settings:display","window_title":"Configurações"}'
achilles call app_find -a '{"query":"Arquivo","role":"MenuItem"}'
```

Chamadas CLI são processos independentes. Para manter `app_attach`, referências e screenshots entre operações, use o MCP, a API local ou um workflow.

## Política local

O arquivo `%LOCALAPPDATA%\Achilles\policy.yaml` pode restringir o runtime:

```yaml
desktop:
  allow_apps:
    - notepad.exe
    - code.exe
  deny_apps:
    - credentialuibroker.exe
  deny_window_titles:
    - "*senha*"
  read_only: false
  allow_launch: true
  allow_close: true
  allow_coordinate_actions: false
```

`allow_apps` e `deny_apps` aceitam padrões glob. O alvo é verificado novamente depois que PID e handle são resolvidos. Processos de logon, credenciais e UAC são bloqueados por padrão.

`app_launch` aceita exatamente um dos campos `executable`, `app_user_model_id` ou `uri`. URIs web, `file:`, `javascript:` e `data:` são recusadas; use as ferramentas de navegador para HTTP(S).

## Isolamento e limites

O processo principal inicia um worker oculto por stdio privado. Objetos COM/UIA e snapshots vivem no worker; uma falha dele retorna erro recuperável sem corromper o transporte MCP.

Screenshots de até 600 kB são enviados também como conteúdo de imagem MCP. Acima desse limite, a resposta mantém caminho, hash e metadados; prefira JPEG quando uma janela muito grande precisar ser vista diretamente pelo agente.

Não são suportados:

- área de trabalho segura, UAC e tela de logon;
- janelas de processo elevado quando o Achilles não possui o mesmo nível;
- conteúdo protegido por DRM;
- jogos e aplicativos protegidos por anti-cheat;
- interfaces remotas sem árvore acessível ou imagem capturável.

O fallback visual não usa coordenadas antigas: ele exige screenshot da mesma janela, dentro do prazo e sem alteração de bounds.
