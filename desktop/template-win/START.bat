@echo off
chcp 65001 >nul
title Yingzhi - RadioCheck
cd /d "%~dp0"

rem pick a free port starting at 8901
set PORT=8901
:findport
netstat -ano | findstr /c:":%PORT% " >nul 2>&1
if errorlevel 1 goto run
set /a PORT+=1
if %PORT% gtr 8960 goto noport
goto findport

:run
echo.
echo   Yingzhi - RadioCheck
echo   http://127.0.0.1:%PORT%/index.html
echo.
echo   Keep this window open while you use the site.
echo   Close it to stop the server.
echo.
start "" cmd /c "timeout /t 3 >nul & start http://127.0.0.1:%PORT%/index.html"
python\python.exe -m http.server %PORT% --bind 127.0.0.1 --directory site
if errorlevel 1 (
  echo   Bundled runtime failed, trying system Python...
  python -m http.server %PORT% --bind 127.0.0.1 --directory site
)
goto end

:noport
echo.
echo   Ports 8901-8960 are all in use. Close some apps and try again.
pause

:end
