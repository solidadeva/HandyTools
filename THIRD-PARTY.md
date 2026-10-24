# Third-party components

This source package builds on the user's existing MinimalConvert and SimpleDownloader projects.

Runtime dependencies are PySide6 / Qt (LGPLv3 / GPLv3 / commercial options), Pillow and pillow-heif / libheif. Their distributions include their respective licenses. PyInstaller is a build dependency. FFmpeg, yt-dlp and Deno are downloaded separately from their upstream distributions; their own licenses apply. FFmpeg's distributed LICENSE is retained alongside installed binaries.

Before redistributing a built executable, retain the third-party license notices included by the runtime distributions and comply with the applicable Qt and media library distribution terms.

Qt documentation: https://doc.qt.io/qtforpython-6/
FFmpeg builds: https://www.gyan.dev/ffmpeg/builds/
yt-dlp: https://github.com/yt-dlp/yt-dlp
Deno: https://github.com/denoland/deno


## GenyConnect launcher entry

The GenyConnect name and official app icon identify the independent app downloaded directly from https://github.com/genyleap/GenyConnect. They belong to Genyleap Labs; branding is All Rights Reserved and is not part of the GPL grant for GenyConnect source. This launcher integration does not imply endorsement or affiliation. GenyConnect binaries are not bundled or modified by Handy Tools App.

Icon provenance: `GenyConnect.iconset/icon_256x256.png`, upstream Git blob `483f392ed42532e84546a8685191c0e7ccbb93a0`, retained unchanged as `assets/icons/genyconnect.png`. Upstream notices: https://github.com/genyleap/GenyConnect/blob/main/NOTICE and https://github.com/genyleap/GenyConnect/blob/main/LICENSE.
