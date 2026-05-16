param(
    [switch]$InstallPyInstaller,
    [switch]$NoExeIcon
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$AssetDir = Join-Path $ProjectRoot "assets"
$IconPath = Join-Path $AssetDir "SilentScreenAlarm.ico"
$DistDir = Join-Path $ProjectRoot "release"
$BuildId = [System.Guid]::NewGuid().ToString("N")
$WorkDir = Join-Path $ProjectRoot ".pyinstaller-work-$BuildId"
$SpecDir = Join-Path $ProjectRoot ".pyinstaller-spec-$BuildId"
$ExePath = Join-Path $DistDir "SilentScreenAlarm.exe"

New-Item -ItemType Directory -Force -Path $AssetDir | Out-Null
New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null
New-Item -ItemType Directory -Force -Path $SpecDir | Out-Null

function New-SilentScreenIcon {
    param([string]$Path)

    Add-Type -AssemblyName System.Drawing
    $bitmap = New-Object System.Drawing.Bitmap 256, 256
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.Clear([System.Drawing.Color]::Transparent)

    $blue = New-Object System.Drawing.SolidBrush ([System.Drawing.ColorTranslator]::FromHtml("#2563eb"))
    $lightBlue = New-Object System.Drawing.SolidBrush ([System.Drawing.ColorTranslator]::FromHtml("#93c5fd"))
    $white = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::White)
    $darkPen = New-Object System.Drawing.Pen ([System.Drawing.ColorTranslator]::FromHtml("#0f172a")), 16
    $darkPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
    $darkPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round

    $graphics.FillEllipse($lightBlue, 28, 22, 66, 56)
    $graphics.FillEllipse($lightBlue, 162, 22, 66, 56)
    $graphics.FillEllipse($blue, 42, 44, 172, 172)
    $graphics.FillEllipse($white, 72, 74, 112, 112)
    $graphics.DrawLine($darkPen, 128, 128, 128, 84)
    $graphics.DrawLine($darkPen, 128, 128, 164, 148)
    $graphics.DrawLine($darkPen, 92, 206, 66, 232)
    $graphics.DrawLine($darkPen, 164, 206, 190, 232)

    $pngStream = New-Object System.IO.MemoryStream
    $bitmap.Save($pngStream, [System.Drawing.Imaging.ImageFormat]::Png)
    $pngBytes = $pngStream.ToArray()

    $fileStream = [System.IO.File]::Create($Path)
    $writer = New-Object System.IO.BinaryWriter($fileStream)
    $writer.Write([UInt16]0)
    $writer.Write([UInt16]1)
    $writer.Write([UInt16]1)
    $writer.Write([byte]0)
    $writer.Write([byte]0)
    $writer.Write([byte]0)
    $writer.Write([byte]0)
    $writer.Write([UInt16]1)
    $writer.Write([UInt16]32)
    $writer.Write([UInt32]$pngBytes.Length)
    $writer.Write([UInt32]22)
    $writer.Write($pngBytes)
    $writer.Close()
    $fileStream.Close()

    $graphics.Dispose()
    $bitmap.Dispose()
    $pngStream.Dispose()
}

New-SilentScreenIcon -Path $IconPath

python -m PyInstaller --version *> $null
if ($LASTEXITCODE -ne 0) {
    if (-not $InstallPyInstaller) {
        Write-Host "PyInstaller is not installed."
        Write-Host "Run this once to install and build:"
        Write-Host "  .\build_windows.ps1 -InstallPyInstaller"
        exit 1
    }
    python -m pip install --upgrade pyinstaller
}

$pyinstallerArgs = @(
    "--noconfirm",
    "--clean",
    "--onefile",
    "--windowed",
    "--workpath", $WorkDir,
    "--specpath", $SpecDir,
    "--distpath", $DistDir,
    "--name", "SilentScreenAlarm"
)

if (-not $NoExeIcon) {
    $pyinstallerArgs += @("--icon", $IconPath)
}

$pyinstallerArgs += "$ProjectRoot\alarm.py"

python -m PyInstaller @pyinstallerArgs

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Build failed."
    if (-not $NoExeIcon) {
        Write-Host "If Windows blocks icon resource stamping, try:"
        Write-Host "  powershell -NoProfile -ExecutionPolicy Bypass -File .\build_windows.ps1 -NoExeIcon"
    }
    exit $LASTEXITCODE
}

if (-not (Test-Path $ExePath)) {
    throw "Build finished but the executable was not found at $ExePath"
}

Write-Host ""
Write-Host "Build complete:"
Write-Host "  $ExePath"
Write-Host ""
Write-Host "Persistent alarm data will be stored next to the executable as alarms.json."
