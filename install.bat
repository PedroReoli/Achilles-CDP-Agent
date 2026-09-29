@echo off
setlocal
echo ===================================================
echo     ACHILLES CDP AGENT — INSTALADOR WINDOWS
echo ===================================================
echo.

echo [1/2] Instalando pacote achilles em modo editavel...
python -m pip install -e .
if errorlevel 1 (
    echo [ERRO] Falha na instalacao. Verifique o Python e o ambiente virtual.
    exit /b 1
)

echo.
echo [2/2] Validando a instalacao...
python -m achilles doctor
if errorlevel 1 (
    echo [ERRO] O diagnostico falhou.
    exit /b 1
)

echo.
echo ===================================================
echo   INSTALACAO CONCLUIDA COM SUCESSO!
echo.
echo   Use no ambiente Python atual:
echo.
echo       python -m achilles
echo.
echo ===================================================
