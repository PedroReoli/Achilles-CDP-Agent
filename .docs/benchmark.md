# Benchmark local de CDP

Execute após instalar o pacote em modo editável e o Chromium do Playwright:

```powershell
python -m pip install -e ".[test]"
python -m playwright install chromium
python scripts/benchmark.py --samples 20 --elements 50 --output benchmark.json
```

O script abre um Chromium descartável em porta dinâmica, cria uma página local via `set_content` e conecta uma instância nova de `ApplicationServices`. Não visita sites externos nem lê o perfil persistente do usuário. Mede separadamente a partida do navegador, o primeiro attach CDP, a primeira leitura e o primeiro snapshot. Após duas operações de aquecimento, mede `snapshot`, `read` e clique em cada amostra. Confere o contador da página a cada série e encerra serviço, navegador e driver no final.

O JSON contém sistema operacional, Python, Playwright, Chromium, quantidade de elementos e amostras. Para cada operação aquecida, informa p50, p95, mínimo e máximo em milissegundos. O p95 usa o posto mais próximo na série ordenada; rode pelo menos 20 amostras para uma leitura mais útil da cauda. Compare resultados apenas com a mesma fixture, versão de navegador e máquina semelhante.

A seção `size_comparison` compara os caracteres do HTML da fixture com o texto compacto de `snapshot` e o Markdown de `read`. A contagem de tokens é **estimada** por quatro caracteres por token; não representa tokenização real nem custo de um modelo específico. As chamadas Playwright continuam trafegando por CDP. O benchmark mede o caminho de serviço completo, incluindo validação, serialização local e verificação após o clique.

Este benchmark não estabelece um limite universal de 100 ms: páginas reais, iframes, desafios, rede e tempo de espera do locator variam. Use o JSON como linha de base antes de alterar os caminhos de observação ou ação.
