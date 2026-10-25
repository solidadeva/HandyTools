Handy Tools App v0.4.2

- Fix the Windows distribution trap behind the missing `_internal/python312.dll` error when the old EXE was moved by itself.
- Build-Windows.bat now produces a self-contained, single-file `dist/portable/HandyToolsApp.exe`; Python and a neighboring `_internal` folder are not required.
- Automatically copy only the built EXE to a separate folder with spaces and verify that the launcher, both tools, Settings, native HEIF imports, vector icons and bundled resources start successfully.
- Build and validate the Windows x64 EXE in GitHub Actions, then publish it with a SHA-256 checksum alongside the source ZIP and incremental-update manifest.

Existing source users: update through Settings, then run Build-Windows.bat again to replace the old build. Existing EXE users: download the new EXE release asset. An old onedir EXE still requires its complete original folder; a desktop shortcut is safe. Frozen EXE per-file updating remains unsupported.
