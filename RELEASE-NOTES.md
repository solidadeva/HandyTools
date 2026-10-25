Handy Tools App v0.4.4 — macOS edition

- Native macOS 15+ app/DMG builds for Apple Silicon arm64 and Intel x86_64, alongside Windows x64.
- Bundle native FFmpeg, FFprobe, Deno, yt-dlp and its JS challenge provider; no Python/Homebrew installation needed by Mac users.
- Add an isolated native downloader on macOS with MP3 or H.264/yuv420p + AAC MP4 output verification, original-file preservation, progress and process-tree cancellation. Windows keeps its existing downloader engine.
- Detect bundled media tools and use macOS app-data paths; display MAC in the launcher footer.
- Mac Settings selects the correct architecture's release, verifies the DMG size/SHA-256 and opens the installer. Drag the new app to Applications; automatic Mac app replacement is not implemented.
- macOS CI validates each relocated app with a clean PATH, bundled binaries, real FFmpeg conversion, native MP4 and MP3 downloads from a local test server, ad-hoc signatures and DMG integrity.

Install: choose macOS-arm64 for M1 and newer, or macOS-x86_64 for Intel. Open the DMG and drag HandyToolsApp to Applications. These builds are ad-hoc signed and are not Apple notarized. If first launch is blocked, review the download source and use System Settings → Privacy & Security → Open Anyway for this app. macOS 15 or later is required.

Windows: update through Settings as before. Analytics/installation tracking has not been added.
