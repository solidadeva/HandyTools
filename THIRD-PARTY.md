# Third-party components

This source package builds on the user's existing MinimalConvert and SimpleDownloader projects.

Runtime dependencies are PySide6 / Qt (LGPLv3 / GPLv3 / commercial options), Pillow and pillow-heif / libheif. Their distributions include their respective licenses. PyInstaller is a build dependency. The Windows edition downloads FFmpeg, yt-dlp and Deno separately from their upstream distributions; the Mac edition bundles FFmpeg/FFprobe, Deno and yt-dlp/yt-dlp-ejs; their own licenses apply. FFmpeg's distributed LICENSE is retained alongside installed binaries.

Before redistributing a built executable, retain the third-party license notices included by the runtime distributions and comply with the applicable Qt and media library distribution terms.

Qt documentation: https://doc.qt.io/qtforpython-6/
FFmpeg builds: https://www.gyan.dev/ffmpeg/builds/
yt-dlp: https://github.com/yt-dlp/yt-dlp
Deno: https://github.com/denoland/deno


## GenyConnect launcher entry

The GenyConnect name and official app icon identify the independent app downloaded directly from https://github.com/genyleap/GenyConnect. They belong to Genyleap Labs; branding is All Rights Reserved and is not part of the GPL grant for GenyConnect source. This launcher integration does not imply endorsement or affiliation. GenyConnect binaries are not bundled or modified by Handy Tools App.

Icon provenance: `GenyConnect.iconset/icon_256x256.png`, upstream Git blob `483f392ed42532e84546a8685191c0e7ccbb93a0`, retained unchanged as `assets/icons/genyconnect.png`. Upstream notices: https://github.com/genyleap/GenyConnect/blob/main/NOTICE and https://github.com/genyleap/GenyConnect/blob/main/LICENSE.

## macOS bundle

The macOS build recipe in `build_macos.py` and `.github/workflows/release.yml` collects native FFmpeg/FFprobe and Deno from Homebrew and packages Python dependencies from requirements.txt. FFmpeg is GPL software; its full corresponding upstream source and build configuration are available at https://ffmpeg.org/download.html and https://github.com/Homebrew/homebrew-core/blob/HEAD/Formula/f/ffmpeg.rb. Deno source/license: https://github.com/denoland/deno. yt-dlp and yt-dlp-ejs source/licenses: https://github.com/yt-dlp/yt-dlp and https://github.com/yt-dlp/ejs. Homebrew dependency licenses are available with their upstream projects and Homebrew formulae. Apple Developer signing/notarization is not included; local ad-hoc signatures are used for native code integrity.
