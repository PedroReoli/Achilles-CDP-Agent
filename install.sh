#!/usr/bin/env bash
set -e

echo "==================================================="
echo "    ACHILLES CDP AGENT — INSTALADOR UNIX (LINUX/MAC)"
echo "==================================================="
echo ""

echo "[1/2] Instalando dependências e pacote achilles em modo editável..."
python3 -m pip install -e ".[test]"

echo ""
echo "[2/2] Validando comando global 'achilles'..."
if command -v achilles &> /dev/null; then
    echo "[OK] Comando 'achilles' disponível diretamente no seu PATH!"
else
    echo "[INFO] Pacote instalado. Se 'achilles' não for encontrado, adicione ~/.local/bin ao seu PATH:"
    echo "       export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo "       Ou execute: python3 -m achilles"
fi

echo ""
echo "==================================================="
echo "  INSTALAÇÃO CONCLUÍDA COM SUCESSO!"
echo "==================================================="
