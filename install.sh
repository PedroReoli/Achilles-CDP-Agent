#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "==================================================="
echo "    ACHILLES CDP AGENT - INSTALADOR UNIX"
echo "==================================================="

if ! command -v uv >/dev/null 2>&1; then
  echo "[ERRO] uv não encontrado. Instale por https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi

echo "[1/3] Instalando ferramenta isolada com Python 3.11+..."
uv tool install --force --python 3.11 .

echo "[2/3] Verificando o diretório de executáveis..."
ACHILLES_BIN="${UV_TOOL_BIN_DIR:-$HOME/.local/bin}"
export PATH="$ACHILLES_BIN:$PATH"
if ! command -v achilles >/dev/null 2>&1; then
  echo "[ERRO] Adicione $ACHILLES_BIN ao PATH do shell e execute novamente." >&2
  exit 1
fi

echo "[3/3] Validando executável e diagnóstico..."
achilles --version
achilles doctor

echo "Instalação concluída. Abra um novo terminal antes de configurar o MCP."
