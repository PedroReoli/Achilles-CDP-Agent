#!/usr/bin/env bash
set -e

echo "==================================================="
echo "    ACHILLES CDP AGENT — INSTALADOR UNIX (LINUX/MAC)"
echo "==================================================="
echo ""

echo "[1/2] Instalando pacote achilles em modo editável..."
python3 -m pip install -e .

echo ""
echo "[2/2] Validando a instalação..."
python3 -m achilles doctor

echo ""
echo "==================================================="
echo "  INSTALAÇÃO CONCLUÍDA COM SUCESSO!"
echo "  Use: python3 -m achilles"
echo "==================================================="
