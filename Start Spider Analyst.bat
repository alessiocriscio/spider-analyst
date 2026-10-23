@echo off
rem Spider Analyst for Windows: double-click, or run  py launch.py
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 launch.py %*
  goto end
)
where python >nul 2>nul
if %errorlevel%==0 (
  python launch.py %*
  goto end
)
echo Python 3.10 or newer is required: https://www.python.org/downloads/windows/
echo In the installer tick "Add python.exe to PATH", then start Spider Analyst again.
start "" https://www.python.org/downloads/windows/
:end
pause
