@echo off
setlocal
echo ===================================================
echo     ACHILLES CDP AGENT — INSTALADOR WINDOWS
echo ===================================================
echo.

echo [1/2] Instalando dependencias e pacote achilles em modo editavel...
python -m pip install -e ".[test]"

echo.
echo [2/2] Validando comando global 'achilles'...
where achilles >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [OK] Comando 'achilles' disponivel diretamente no seu PATH!
) else (
    echo [INFO] Pacote instalado. Caso 'achilles' nao seja reconhecido,
    echo        certifique-se de que a pasta Scripts do seu Python esta no PATH.
    echo        Voce tambem pode executar diretamente: python -m achilles
)

echo.
echo ===================================================
echo   INSTALACAO CONCLUIDA COM SUCESSO!
echo.
echo   Agora voce pode abrir qualquer CMD ou PowerShell
echo   e digitar simplesmente:
echo.
echo       achilles
echo.
echo ===================================================
pause
