function Read-MediaInfo([string]$Path, [string]$Probe) {
    $probeError = Join-Path (Split-Path -Parent $JobFile) 'probe-error.txt'
    $json = & $Probe -v error -show_streams -show_format -of json $Path 2> $probeError
    if ($LASTEXITCODE -ne 0) { throw 'FFprobe could not read the media file.' }
    return (($json -join "`n") | ConvertFrom-Json)
}

function Convert-PremiereVideo([string]$Source, [string]$Folder, [string]$Bin) {
    $ffmpeg = Join-Path $Bin 'ffmpeg.exe'
    $probe = Join-Path $Bin 'ffprobe.exe'
    $media = Read-MediaInfo $Source $probe
    $videos = @($media.streams | Where-Object { $_.codec_type -eq 'video' -and $_.disposition.attached_pic -ne 1 })
    if ($videos.Count -eq 0) { throw 'No video stream was found.' }
    $videoIndex = [string]$videos[0].index
    $duration = 0.0
    [double]::TryParse([string]$media.format.duration, [Globalization.NumberStyles]::Float,
        [Globalization.CultureInfo]::InvariantCulture, [ref]$duration) | Out-Null
    $baseName = [IO.Path]::GetFileNameWithoutExtension($Source) + ' - H264'
    $final = Join-Path $Folder ($baseName + '.mp4')
    $number = 2
    while (Test-Path -LiteralPath $final) {
        $final = Join-Path $Folder ($baseName + ' (' + $number + ').mp4')
        $number++
    }
    # Private temporary output: a canceled/failed encode is never the final MP4.
    $temp = Join-Path $Folder ('.sd-' + [guid]::NewGuid().ToString('N') + '.working.mp4')
    $encodeError = Join-Path (Split-Path -Parent $JobFile) 'encode-error.txt'
    try {
        Report 'CONVERT|START'
        # Re-encode explicitly even when the downloaded container is already MP4.
        # Padding supports odd source dimensions without cropping image content.
        $encodeArgs = @('-hide_banner','-nostdin','-loglevel','error','-n','-i',$Source,
            '-map',('0:' + $videoIndex),'-map','0:a:0?','-sn','-dn',
            '-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p',
            '-vf','pad=ceil(iw/2)*2:ceil(ih/2)*2','-fps_mode','cfr',
            '-tag:v','avc1','-c:a','aac','-b:a','192k','-ar','48000',
            '-movflags','+faststart','-progress','pipe:1','-nostats',$temp)
        & $ffmpeg @encodeArgs 2> $encodeError | ForEach-Object {
            if ($_ -match '^out_time_us=(\d+)$' -and $duration -gt 0) {
                $percent = [Math]::Min(99, ([double]$Matches[1] / 1000000.0 / $duration * 100))
                Report ('CV|' + $percent.ToString('F1', [Globalization.CultureInfo]::InvariantCulture))
            }
        }
        if ($LASTEXITCODE -ne 0) {
            if (Test-Path -LiteralPath $encodeError) { Report (Get-Content -LiteralPath $encodeError -Raw) }
            throw 'H.264 conversion failed. Downloaded source is retained for retry.'
        }
        Report 'CONVERT|VERIFY'
        $result = Read-MediaInfo $temp $probe
        $v = @($result.streams | Where-Object { $_.codec_type -eq 'video' })
        $a = @($result.streams | Where-Object { $_.codec_type -eq 'audio' })
        $sourceAudio = @($media.streams | Where-Object { $_.codec_type -eq 'audio' })
        if ($v.Count -ne 1 -or $v[0].codec_name -ne 'h264' -or $v[0].pix_fmt -ne 'yuv420p' -or
            $v[0].codec_tag_string -ne 'avc1' -or ($a.Count -gt 0 -and $a[0].codec_name -ne 'aac') -or
            ($sourceAudio.Count -gt 0 -and $a.Count -eq 0)) {
            throw 'Final codec verification failed. Downloaded source is retained.'
        }
        # Move without -Force, so existing user files cannot be overwritten.
        Move-Item -LiteralPath $temp -Destination $final
        Report ('FILE|' + $final)
        # Keep the downloaded source for retries and future exports.
    } finally {
        if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue }
    }
}
