@echo off
color 02
echo vzlom_vifi_network
echo MTSRouter_002865 = password
echo.
echo [!] Инициализация взлома... Подождите 10 минут...
echo.

set /a counter=0
:loop
set /a counter+=1
echo %random%%random%%random%%random%%random%
if %counter% geq 1000 goto end
timeout /t 1 >nul
goto loop
:end
echo.
echo ---------------------------------
echo [ВЗЛОМ ЗАВЕРШЕН]
echo ПАРОЛЬ НАЙДЕН: 87654321
echo ---------------------------------
pause
