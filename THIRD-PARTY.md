# Third-party components

This source package builds on the user's existing MinimalConvert and SimpleDownloader projects.

Runtime dependencies are PySide6 / Qt (LGPLv3 / GPLv3 / commercial options), Pillow and pillow-heif / libheif. Their distributions include their respective licenses. PyInstaller is a build dependency. FFmpeg, yt-dlp and Deno are downloaded separately from their upstream distributions; their own licenses apply. FFmpeg's distributed LICENSE is retained alongside installed binaries.

Before redistributing a built executable, retain the third-party license notices included by the runtime distributions and comply with the applicable Qt and media library distribution terms.

Qt documentation: https://doc.qt.io/qtforpython-6/
FFmpeg builds: https://www.gyan.dev/ffmpeg/builds/
yt-dlp: https://github.com/yt-dlp/yt-dlp
Deno: https://github.com/denoland/deno
