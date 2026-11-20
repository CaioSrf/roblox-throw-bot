@echo off
chcp 65001 >nul
title Configurador de Sessao Isolada (RDP Local / Windows Sandbox) para o Bot Roblox

echo ============================================================================
echo   CONFIGURADOR DE SESSAO ISOLADA PARA O BOT ROBLOX (WINDOWS 10 PRO)
echo ============================================================================
echo.
echo Verificando privilegios de Administrador...
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [!] Solicitando permissao de Administrador...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo.
echo Escolha como deseja rodar o Roblox isolado em segundo plano:
echo   [1] Criar 2o Usuario Local 'RobloxBot' + Ativar Servico RDP Local (Recomendado - Usa sua RX 5700 XT)
echo   [2] Ativar o Windows Sandbox nativo do Windows 10 Pro (Requer 1 reinicializacao do Windows)
echo   [3] Fazer AMBOS (Criar usuario 'RobloxBot' + Ativar Windows Sandbox)
echo.
set /p opcao="Digite 1, 2 ou 3: "

if "%opcao%"=="1" goto :setup_user
if "%opcao%"=="2" goto :setup_sandbox
if "%opcao%"=="3" goto :setup_both
goto :setup_user

:setup_user
echo.
echo [+] Criando usuario local 'RobloxBot' (Senha: Bot@12345)...
net user RobloxBot Bot@12345 /add /Y >nul 2>&1
net user RobloxBot Bot@12345 >nul 2>&1
net localgroup Administradores RobloxBot /add >nul 2>&1
net localgroup Administrators RobloxBot /add >nul 2>&1
net localgroup "Usuários da área de trabalho remota" RobloxBot /add >nul 2>&1
net localgroup "Remote Desktop Users" RobloxBot /add >nul 2>&1

echo [+] Ativando Área de Trabalho Remota (TermService) no Windows 10 Pro...
reg add "HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server" /v fDenyTSConnections /t REG_DWORD /d 0 /f >nul
reg add "HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server" /v fSingleSessionPerUser /t REG_DWORD /d 0 /f >nul
sc config TermService start= auto >nul
net start TermService >nul 2>&1
netsh advfirewall firewall set rule group="remote desktop" new enable=Yes >nul 2>&1
netsh advfirewall firewall set rule group="área de trabalho remota" new enable=Yes >nul 2>&1

echo [+] Copiando o Bot para a Area de Trabalho publica (acessivel pelo usuario RobloxBot)...
mkdir "C:\Users\Public\Desktop\RobloxThrowBot" >nul 2>&1
xcopy /E /I /Y "%~dp0*" "C:\Users\Public\Desktop\RobloxThrowBot\" >nul

echo.
echo [OK] Usuario 'RobloxBot' (Senha: Bot@12345) criado e pasta compartilhada em:
echo      C:\Users\Public\Desktop\RobloxThrowBot
if "%opcao%"=="1" goto :fim
goto :setup_sandbox

:setup_sandbox
echo.
echo [+] Ativando o recurso Windows Sandbox (Containers-DisposableClientVM) do Windows 10 Pro...
dism /online /enable-feature /featurename:Containers-DisposableClientVM /all /norestart
echo.
echo [OK] Windows Sandbox ativado! (Se for a primeira vez, reinicie o PC para o Windows Sandbox abrir).

:fim
echo.
echo ============================================================================
echo   CONFIGURACAO CONCLUIDA COM SUCESSO!
echo ============================================================================
pause
