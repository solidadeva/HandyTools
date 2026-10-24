@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto missing
".venv\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onedir --windowed --collect-all pillow_heif --add-data "downloader;downloader" --icon "assets\handy.ico" --name HandyToolsApp launch.pyw
if errorlevel 1 goto failed
copy /y "README-fa.md" "dist\HandyToolsApp\README-fa.md" >nul
copy /y "THIRD-PARTY.md" "dist\HandyToolsApp\THIRD-PARTY.md" >nul
echo Ready: dist\HandyToolsApp\HandyToolsApp.exe
echo Keep the ENTIRE HandyToolsApp folder together. Python is not needed on the target PC.
pause
exit /b 0
:missing
echo Run Install.bat first.
pause
exit /b 1
:failed
echo Build failed. Check the error above.
pause
exit /b 1
