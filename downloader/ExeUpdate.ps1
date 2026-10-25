param([Parameter(Mandatory=$true)][string]$Config)
$ErrorActionPreference = 'Stop'
$stage = Split-Path -Parent $Config
$result = Join-Path $stage 'result.json'
$replacement = $null
$backup = $null
$replaced = $false
$cfg = $null
$guard = $null
$lockPath = $null
function Save-Result([bool]$ok, [string]$message) {
    @{ ok=$ok; message=$message } | ConvertTo-Json | Set-Content -LiteralPath $result -Encoding UTF8
}
function Replace-Retry([string]$source, [string]$destination, [string]$old) {
    # A PyInstaller one-file bootloader can hold the EXE briefly after Python exits.
    for ($attempt=0; $attempt -lt 120; $attempt++) {
        try {
            if ($old) { [IO.File]::Replace($source, $destination, $old) }
            else { [IO.File]::Replace($source, $destination, $null) }
            return
        }
        catch { if ($attempt -eq 119) { throw }; Start-Sleep -Milliseconds 250 }
    }
}
try {
    $cfg = Get-Content -LiteralPath $Config -Raw -Encoding UTF8 | ConvertFrom-Json
    $target = [IO.Path]::GetFullPath([string]$cfg.target)
    $lockPath = $target + '.handy-update.lock'
    $guard = [IO.File]::Open($lockPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    $package = Join-Path $stage 'package.exe'
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { throw 'Installed EXE was not found.' }
    if ((Get-Item -LiteralPath $package).Length -ne [long]$cfg.package.size -or
        (Get-FileHash -LiteralPath $package -Algorithm SHA256).Hash.ToLowerInvariant() -ne $cfg.package.sha256) {
        throw 'The executable update failed checksum verification.'
    }
    $token = [guid]::NewGuid().ToString('N')
    $folder = Split-Path -Parent $target
    $replacement = Join-Path $folder ('.handy-new-' + $token + '.exe')
    $backup = Join-Path $folder ('.handy-previous-' + $token + '.exe')
    [IO.File]::Copy($package, $replacement, $false)
    if ((Get-FileHash -LiteralPath $replacement -Algorithm SHA256).Hash.ToLowerInvariant() -ne $cfg.package.sha256) {
        throw 'The local executable copy failed checksum verification.'
    }
    $parent = Get-Process -Id ([int]$cfg.parentPid) -ErrorAction SilentlyContinue
    if ($parent -and -not $parent.WaitForExit(120000)) { throw 'The app did not exit; update cancelled.' }
    Replace-Retry $replacement $target $backup
    $replaced = $true
    $env:PYINSTALLER_RESET_ENVIRONMENT = '1'
    if ($cfg.smokeReport) {
        # Used only by the Windows integration check, with correctly quoted paths.
        $argsText = '--smoke-test "' + [string]$cfg.smokeReport + '"'
        $started = Start-Process -FilePath $target -WorkingDirectory $folder -ArgumentList $argsText -PassThru
        if (-not $started.WaitForExit(120000) -or $started.ExitCode -ne 0 -or
            -not (Test-Path -LiteralPath ([string]$cfg.smokeReport))) { throw 'Updated EXE startup failed.' }
    } else {
        $started = Start-Process -FilePath $target -WorkingDirectory $folder -PassThru
        if ($started.WaitForExit(3000) -and $started.ExitCode -ne 0) { throw 'Updated EXE exited with an error.' }
    }
    Save-Result $true 'Executable updated and restarted.'
    Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $package -Force -ErrorAction SilentlyContinue
    exit 0
} catch {
    $message = $_.Exception.Message
    if ($replaced -and (Test-Path -LiteralPath $backup)) {
        try {
            Replace-Retry $backup $target $null
            $env:PYINSTALLER_RESET_ENVIRONMENT = '1'
            if (-not $cfg.smokeReport) { Start-Process -FilePath $target -WorkingDirectory (Split-Path -Parent $target) }
            $message += ' The previous EXE has been restored.'
        } catch { $message += ' Restore the previous EXE manually from: ' + $backup }
    }
    Save-Result $false $message
    if (-not $cfg.smokeReport) {
        Add-Type -AssemblyName System.Windows.Forms
        [Windows.Forms.MessageBox]::Show($message, 'Handy Tools App update') | Out-Null
    }
    exit 1
} finally {
    if ($guard) {
        $guard.Dispose()
        Remove-Item -LiteralPath $lockPath -Force -ErrorAction SilentlyContinue
    }
    if ($replacement -and (Test-Path -LiteralPath $replacement)) {
        Remove-Item -LiteralPath $replacement -Force -ErrorAction SilentlyContinue
    }
}
