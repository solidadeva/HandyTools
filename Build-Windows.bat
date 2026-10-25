@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto missing
".venv\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" build_windows.py
if errorlevel 1 goto failed
echo Ready: dist\portable\HandyToolsApp.exe
echo This is a single-file EXE. You can copy it to your Desktop.
echo Old dist\HandyToolsApp builds still require their entire _internal folder.
if /i not "%~1"=="--no-pause" pause
exit /b 0
:missing
echo Run Install.bat first.
if /i not "%~1"=="--no-pause" pause
exit /b 1
:failed
echo Build or standalone startup test failed. Check the error above.
if /i not "%~1"=="--no-pause" pause
exit /b 1
