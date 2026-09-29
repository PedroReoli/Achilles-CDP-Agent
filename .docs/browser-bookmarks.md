# Favoritos nativos no Chrome e Edge

O Achilles usa Playwright para manter a sessão CDP e uma extensão Manifest V3 mínima para acessar `chrome.bookmarks`. A extensão pede apenas a permissão `bookmarks`. O CDP não oferece uma API própria para criar, editar ou remover favoritos. Nenhum arquivo `Bookmarks` do perfil é editado diretamente.

## Preparar e instalar

```powershell
achilles --extension
```

O comando cria `Achilles Browser Bridge.zip` e a pasta descompactada `Achilles Browser Bridge` na Área de Trabalho. Mostra um toast no Windows quando as notificações estiverem disponíveis e imprime as instruções no terminal. O ZIP serve para transportar ou guardar os arquivos. O Chrome e o Edge instalam **a pasta**, não o ZIP.

1. Abra `chrome://extensions` ou `edge://extensions` **no mesmo perfil que o Achilles controla**.
2. Ative **Modo do desenvolvedor** e escolha **Carregar sem compactação / Load unpacked**.
3. Selecione a pasta `Achilles Browser Bridge` criada na Área de Trabalho.
4. Confirme o ID `iaheffblcnihpbdecmnkioimgdjjffgo` e teste com `achilles bookmarks list`.

Se você copiar o ZIP para outra máquina, extraia-o primeiro para uma pasta permanente e selecione essa pasta. Mantenha a pasta no local escolhido: o navegador carrega a extensão diretamente dela. O Achilles abre normalmente mesmo sem a extensão; apenas as operações de favoritos precisam dela. O perfil criado automaticamente pelo Achilles é separado do perfil pessoal. Se a porta CDP já estiver ocupada, Achilles se conecta ao navegador que está nessa porta, então instale a extensão nele.

O Chrome é o padrão. Para iniciar o Edge automaticamente no PowerShell:

```powershell
$env:ACHILLES_BROWSER = 'edge'
achilles bookmarks list
```

`ACHILLES_BROWSER` controla apenas qual executável e perfil o Achilles inicia quando a porta CDP está fechada. Se já há navegador na porta configurada, Achilles se conecta a ele. Use portas diferentes para sessões simultâneas de Chrome e Edge.

## CLI

```powershell
achilles bookmarks list
achilles bookmarks list --parent-id <id-da-pasta>
achilles bookmarks search "Achilles"
achilles bookmarks create "Achilles" "https://example.org"
achilles bookmarks update <id> --title "Novo título"
achilles bookmarks remove <id>
```

Use `achilles bookmarks --cdp-port 9223 ...` para outra porta. As mesmas operações estão disponíveis como ferramentas MCP e endpoints REST: `browser_bookmarks_list`, `browser_bookmarks_search`, `browser_bookmarks_create`, `browser_bookmarks_update` e `browser_bookmarks_remove`.

`list` sem pasta mostra as pastas principais. `create` sem `parent_id` usa a barra de favoritos. `remove` remove um favorito ou uma pasta vazia; não apaga pastas inteiras recursivamente. Criação e edição de URL aceitam apenas HTTP(S) sem credenciais. Resultados limitam a quantidade de itens e ocultam segredos reconhecidos nas URLs.

O código da extensão não recebe mensagens de páginas web nem mantém servidor local. A chamada às APIs de favoritos acontece em uma página da extensão aberta e fechada pelo Achilles dentro da sessão CDP. Instalar a extensão concede ao Achilles acesso de leitura e escrita aos favoritos do perfil escolhido.
