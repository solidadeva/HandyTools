# Handy Tools App

A compact Windows launcher for **Easy Downloader** and **Easy Converter**, with shared light/dark themes and independent tool windows.

![Launcher](assets/home-dark.png)

## Install

Download the latest **HandyToolsApp-Windows** ZIP from [Releases](https://github.com/solidadeva/HandyTools/releases/latest), extract it, run `Install.bat` once, then `Start.vbs`. Requires 64-bit Python 3.11 or later. Alternatively, download the Windows-x64 `.exe` release asset for a standalone app requiring no Python installation. It can be moved by itself, including to the Desktop.

## Updates

Open **Settings (gear) → Check for updates**. The updater compares SHA-256 hashes and downloads only changed app files from the immutable release commit. FFmpeg, media files, settings and the existing Python environment are retained. New dependencies are installed only when requirements change. Installation waits for the app to close, backs up changed files, applies the update and restarts. On failure, app files are rolled back; dependency-environment changes cannot be rolled back automatically.

Versions 0.1/0.2 need one initial upgrade to 0.3.0 to obtain the updater. Frozen EXE updates are not supported yet.

## Launcher

Version 0.4.0 adds the official **GenyConnect** launcher entry. It starts uninstalled; click to download and install the correct official platform package. SHA-256 is checked before execution, and an existing installation opens directly. GenyConnect binaries are not bundled. Windows uses the upstream NSIS installer and normal UAC; macOS uses a user Applications installation, and Linux uses the official AppImage. Native Windows/macOS installation still needs platform validation.

The drawer now has continuous corners, traffic-light window controls, a sharp lower-right corner with a tiny five-second pulsing resize triangle, and frameless bright/dim app selection with a blue dot.

The v0.3.1 interface uses an Apple-inspired visual language: silver/graphite surfaces, fine separators, blue controls and original continuous-corner gradient icons. Existing structure and behavior are preserved.

- Smaller initial size; drag the lower-right grip to resize. Last size is remembered.
- Mouse wheel, swipe/drag, arrows and Left/Right keys navigate; click or Enter opens a tool.
- Settings controls themes and updates. Donate remains a visual placeholder.
- Converter supports HEIC primary-image decoding and ten output formats.
- Downloader explicitly converts video to 8-bit H.264/AAC MP4 for editing.

## Development and releases

Install `requirements.txt`, ensure FFmpeg is on PATH, then run:

```sh
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -p 'test_*.py'
```

Increase `version.py`, update `RELEASE-NOTES.md` and push to `main`. The release workflow tests the app on Linux, builds and validates a standalone EXE on Windows x64, then publishes the EXE, SHA-256 checksum, source ZIP and per-file update manifest. Existing releases are not overwritten.

See [راهنمای فارسی](README-fa.md) and [third-party notices](THIRD-PARTY.md).

## Windows EXE build

Run `Build-Windows.bat` after `Install.bat`. The standalone output is `dist/portable/HandyToolsApp.exe`. The build validates it from an isolated directory containing only that EXE, before creating the release artifact and SHA-256 checksum. GitHub Actions builds and smoke-tests the Windows x64 executable before publishing.

Old onedir builds at `dist/HandyToolsApp/HandyToolsApp.exe` must retain their complete `_internal` directory. A `Failed to load Python DLL ... _internal/python312.dll` error after moving only that old EXE is resolved by restoring the complete folder, creating a shortcut, or rebuilding with the new script. Updating source files does not change an already-built EXE; rebuild or download the new standalone release. Frozen EXE per-file updates remain unsupported.
