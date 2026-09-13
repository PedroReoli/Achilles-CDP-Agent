@echo off
setlocal
echo ===================================================
echo     ACHILLES CDP AGENT — INSTALADOR WINDOWS
echo ===================================================
echo.

echo [1/3] Instalando dependencias e pacote achilles...
pip install -e .

echo.
echo [2/3] Compilando executavel standalone (achilles.exe)...
python packaging/build_exe.py

echo.
echo [3/3] Registrando atalho global 'achilles' no sistema...
set "TARGET_DIR=%LOCALAPPDATA%\Microsoft\WindowsApps"
if exist "%TARGET_DIR%" (
    copy /Y "dist\achilles.exe" "%TARGET_DIR%\achilles.exe" >nul
    echo [OK] achilles.exe copiado para %TARGET_DIR% (Ja esta no seu PATH!)
) else (
    echo [INFO] dist\achilles.exe pronto para uso.
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
