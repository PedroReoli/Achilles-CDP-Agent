@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ===================================================
echo     ACHILLES CDP AGENT - INSTALADOR WINDOWS
echo ===================================================
echo.

set "UV_EXE="
where uv.exe >nul 2>nul && set "UV_EXE=uv.exe"
if not defined UV_EXE if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV_EXE=%USERPROFILE%\.local\bin\uv.exe"
if not defined UV_EXE goto uv_error

echo [1/3] Instalando o Achilles como ferramenta isolada com Python 3.11+...
"%UV_EXE%" tool install --force --python 3.11 .
if errorlevel 1 (
    echo [AVISO] O ambiente pode estar em uso. Tentando atualizacao interna...
    if not exist "%APPDATA%\uv\tools\achilles-cdp\Scripts\python.exe" goto install_error
    "%UV_EXE%" pip install --python "%APPDATA%\uv\tools\achilles-cdp\Scripts\python.exe" .
    if errorlevel 1 goto install_error
)

echo [2/3] Garantindo o diretorio de executaveis no PATH do usuario...
set "ACHILLES_BIN=%USERPROFILE%\.local\bin"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$bin=[IO.Path]::GetFullPath($env:ACHILLES_BIN); $p=[Environment]::GetEnvironmentVariable('Path','User'); $items=@($p -split ';' | Where-Object { $_ -and $_ -ne $bin }); [Environment]::SetEnvironmentVariable('Path',((@($bin)+$items) -join ';'),'User')"
if errorlevel 1 goto path_error
set "PATH=%ACHILLES_BIN%;%PATH%"

echo [3/3] Validando executavel e diagnostico...
if not exist "%ACHILLES_BIN%\achilles.exe" goto shim_error
"%ACHILLES_BIN%\achilles.exe" --version
if errorlevel 1 goto verify_error
"%ACHILLES_BIN%\achilles.exe" doctor
if errorlevel 1 goto verify_error

echo.
echo ===================================================
echo   INSTALACAO CONCLUIDA
echo   Executavel: %ACHILLES_BIN%\achilles.exe
echo   Abra um novo terminal antes de configurar o MCP.
echo ===================================================
exit /b 0

:uv_error
echo [ERRO] uv nao encontrado. Instale em:
echo https://docs.astral.sh/uv/getting-started/installation/
exit /b 1

:install_error
echo [ERRO] Falha ao instalar ou atualizar o pacote Achilles.
exit /b 1

:path_error
echo [ERRO] Pacote instalado, mas nao foi possivel atualizar o PATH.
echo Adicione manualmente: %USERPROFILE%\.local\bin
exit /b 1

:shim_error
echo [ERRO] A instalacao nao criou %ACHILLES_BIN%\achilles.exe.
exit /b 1

:verify_error
echo [ERRO] O executavel foi criado, mas a validacao falhou.
exit /b 1
