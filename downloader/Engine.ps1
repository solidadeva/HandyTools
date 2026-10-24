param([Parameter(Mandatory=$true)][string]$JobFile)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$utf8 = New-Object Text.UTF8Encoding($false)
$job = Get-Content -LiteralPath $JobFile -Raw -Encoding UTF8 | ConvertFrom-Json
function Report([string]$text) { [IO.File]::AppendAllText($job.log, $text + "`n", $utf8) }
function Fetch([string]$url, [string]$path) {
    $temp = $path + '.download'
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $temp -TimeoutSec 600
    Move-Item -LiteralPath $temp -Destination $path -Force
}
try {
    if (-not [Environment]::Is64BitOperatingSystem) { throw 'Windows 64-bit is required.' }
    $bin = if ($job.bin) { [string]$job.bin } else { Join-Path $env:LOCALAPPDATA 'HandyToolsApp\bin' }
    New-Item -ItemType Directory -Path $bin -Force | Out-Null
    $yt = Join-Path $bin 'yt-dlp.exe'
    if ($job.mode -eq 'update') {
        Report 'Updating yt-dlp...'
        Fetch 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe' $yt
        Report 'Update complete.'
        exit 0
    }
    if (-not (Test-Path -LiteralPath $yt)) {
        Report 'First run: downloading yt-dlp...'
        Fetch 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe' $yt
    }
    if (-not (Test-Path (Join-Path $bin 'ffmpeg.exe')) -or -not (Test-Path (Join-Path $bin 'ffprobe.exe'))) {
        Report 'First run: downloading FFmpeg (large download, please wait)...'
        $zip = Join-Path $bin 'ffmpeg.zip'
        Fetch 'https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip' $zip
        $stage = Join-Path $bin ('ffmpeg-' + [guid]::NewGuid().ToString('N'))
        try {
            Expand-Archive -LiteralPath $zip -DestinationPath $stage -Force
            foreach ($name in @('ffmpeg.exe','ffprobe.exe')) {
                $found = Get-ChildItem -LiteralPath $stage -Filter $name -Recurse | Select-Object -First 1
                if (-not $found) { throw "Archive is missing $name" }
                Copy-Item -LiteralPath $found.FullName -Destination (Join-Path $bin ($name + '.new')) -Force
            }
            foreach ($name in @('ffmpeg.exe','ffprobe.exe')) {
                Move-Item -LiteralPath (Join-Path $bin ($name + '.new')) -Destination (Join-Path $bin $name) -Force
            }
        } finally {
            if (Test-Path $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
            Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
        }
    }
    $deno = Join-Path $bin 'deno.exe'
    if (-not (Test-Path -LiteralPath $deno)) {
        Report 'First run: downloading JavaScript runtime for YouTube...'
        $zip = Join-Path $bin 'deno.zip'
        Fetch 'https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip' $zip
        $stage = Join-Path $bin ('deno-' + [guid]::NewGuid().ToString('N'))
        try {
            Expand-Archive -LiteralPath $zip -DestinationPath $stage -Force
            $found = Get-ChildItem -LiteralPath $stage -Filter 'deno.exe' -Recurse | Select-Object -First 1
            if (-not $found) { throw 'Archive is missing deno.exe' }
            Copy-Item -LiteralPath $found.FullName -Destination $deno -Force
        } finally {
            if (Test-Path $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
            Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
        }
    }
    New-Item -ItemType Directory -Path $job.folder -Force | Out-Null
    $pathFile = Join-Path (Split-Path -Parent $JobFile) 'downloaded-path.txt'
    $downloadFolder = [string]$job.folder
    if ($job.quality -ne 'audio') {
        $downloadFolder = Join-Path $job.folder '.HandyTools-source'
        New-Item -ItemType Directory -Path $downloadFolder -Force | Out-Null
    }
    $opts = @('--ignore-config','--no-playlist','--no-color','--newline','--progress','--progress-delta','0.5','--windows-filenames',
        '--no-overwrites','--continue','--socket-timeout','30','--retries','3',
        '--ffmpeg-location',$bin,'--js-runtimes',('deno:' + $deno),
        '--progress-template','download:DL|%(progress._percent_str)s|%(progress._speed_str)s|%(progress._eta_str)s',
        '--print-to-file','after_move:%(filepath)s',$pathFile,'--no-simulate','--encoding','utf-8',
        '-P',$downloadFolder,'-o','%(title).160B [%(id)s].%(ext)s')
    if ($job.quality -eq 'audio') {
        $opts += @('-f','ba/b','-x','--audio-format','mp3','--audio-quality','0')
    } else {
        $cap = ''
        if ($job.quality -match '^\d+$') { $cap = '[height<=' + $job.quality + ']' }
        $format = 'bv' + $cap + '+ba/b' + $cap
        $opts += @('-f',$format,'--merge-output-format','mkv')
    }
    $opts += @('--',[string]$job.url)
    Report 'Connecting...'
    # Argument arrays keep the URL as data; never evaluate it as PowerShell code.
    $ErrorActionPreference = 'Continue'
    & $yt @opts 2>&1 | ForEach-Object { Report ([string]$_) }
    $code = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($code -ne 0) { throw "Download failed (exit $code). Check the log above." }
    if ($job.quality -ne 'audio') {
        . (Join-Path $PSScriptRoot 'Compatibility.ps1')
        if (-not (Test-Path -LiteralPath $pathFile)) { throw 'Download did not return an output file.' }
        $source = (Get-Content -LiteralPath $pathFile -Encoding UTF8 | Select-Object -Last 1)
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw 'Downloaded source was not found.' }
        Convert-PremiereVideo -Source $source -Folder ([string]$job.folder) -Bin $bin
    } else {
        if (Test-Path -LiteralPath $pathFile) {
            Report ('FILE|' + (Get-Content -LiteralPath $pathFile -Encoding UTF8 | Select-Object -Last 1))
        }
    }
    Report 'DONE'
    exit 0
} catch {
    Report ('ERROR: ' + $_.Exception.Message)
    exit 1
}
