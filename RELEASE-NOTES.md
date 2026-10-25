Handy Tools App v0.4.3

- Enable Settings → Check for updates in the portable Windows EXE.
- Select the matching Windows x64 release asset, stream the new executable with progress/cancellation and verify its size, SHA-256 and Windows header before staging it.
- Install only after active tools/installers finish. An independent PowerShell helper waits for the app to exit, checks the staged checksum again, atomically replaces the EXE in its existing location and restarts it with a fresh PyInstaller environment.
- Preserve the old EXE if download/verification fails; restore it if replacement or immediate restart fails. Settings, FFmpeg, GenyConnect and user files are retained.
- Check folder write permissions before closing the app and guard against simultaneous installers.
- Windows CI tests actual EXE replacement/restart with Unicode/spaced paths and stale frozen-process environment, plus rollback and restored-app startup after a deliberately invalid replacement.

EXE v0.4.2 and earlier has no built-in updater: download the v0.4.3 EXE manually once. Future EXE updates are available from Settings. Portable EXE updates download the complete EXE; the Python edition continues to download only changed source files.
