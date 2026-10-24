@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto dependencies
where py >nul 2>nul
if errorlevel 1 goto plainpython
py -3 -m venv .venv
if errorlevel 1 goto failed
goto dependencies
:plainpython
python -m venv .venv
if errorlevel 1 goto failed
:dependencies
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo Ready. Open Start.vbs. The app launches without a console window.
pause
exit /b 0
:failed
echo Setup failed. Install 64-bit Python 3.11 or newer from python.org.
echo Check your internet connection, then run Install.bat again.
pause
exit /b 1
