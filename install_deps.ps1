$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppBin = Join-Path $Root "bin"
$ToolsDir = Join-Path $Root "tools"
$FfmpegDir = Join-Path $ToolsDir "ffmpeg"
$FfmpegBin = Join-Path $FfmpegDir "bin"
$FfmpegExe = Join-Path $FfmpegBin "ffmpeg.exe"
$FfprobeExe = Join-Path $FfmpegBin "ffprobe.exe"
if ((Test-Path (Join-Path $AppBin "ffmpeg.exe")) -and
    (Test-Path (Join-Path $AppBin "ffprobe.exe"))) {
    $env:PATH = "$AppBin;$env:PATH"
}

function Has-Command($Name) {
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Add-PythonToCurrentPath {
    $candidateRoots = @(
        "$env:LOCALAPPDATA\Programs\Python",
        "$env:LOCALAPPDATA\Microsoft\WindowsApps",
        "$env:ProgramFiles\Python312",
        "$env:ProgramFiles\Python313",
        "$env:ProgramFiles\Python314"
    )

    foreach ($root in $candidateRoots) {
        if (-not (Test-Path $root)) { continue }
        $pythonExe = Get-ChildItem -Path $root -Recurse -Filter "python.exe" -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($pythonExe) {
            $pythonDir = $pythonExe.Directory.FullName
            $env:PATH = "$pythonDir;$env:PATH"
            $scriptsDir = Join-Path $pythonDir "Scripts"
            if (Test-Path $scriptsDir) {
                $env:PATH = "$scriptsDir;$env:PATH"
            }
            return
        }
    }
}

function Install-FFmpegPortable {
    New-Item -ItemType Directory -Force -Path $ToolsDir | Out-Null

    if ((Test-Path $FfmpegExe) -and (Test-Path $FfprobeExe)) {
        Write-Host "FFmpeg portable da san sang."
        return
    }

    Write-Host "Dang tai FFmpeg portable..."
    $release = Invoke-RestMethod "https://api.github.com/repos/GyanD/codexffmpeg/releases/latest"
    $asset = $release.assets |
        Where-Object { $_.name -like "*essentials_build.zip" } |
        Select-Object -First 1

    if (-not $asset) {
        throw "Khong tim thay goi FFmpeg essentials_build.zip tren GitHub."
    }

    $ZipPath = Join-Path $ToolsDir $asset.name
    $ExtractDir = Join-Path $ToolsDir "ffmpeg_extract"

    Remove-Item -Recurse -Force $ExtractDir -ErrorAction SilentlyContinue
    Remove-Item -Force $ZipPath -ErrorAction SilentlyContinue

    if (Get-Command "curl.exe" -ErrorAction SilentlyContinue) {
        & curl.exe -L --retry 3 --retry-delay 3 --connect-timeout 20 --max-time 300 --fail -o $ZipPath $asset.browser_download_url
        if ($LASTEXITCODE -ne 0) {
            throw "Tai FFmpeg bang curl.exe khong thanh cong."
        }
    } else {
        Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $ZipPath
    }

    if ((-not (Test-Path $ZipPath)) -or ((Get-Item $ZipPath).Length -le 0)) {
        throw "File FFmpeg tai ve bi rong."
    }
    Expand-Archive -Path $ZipPath -DestinationPath $ExtractDir -Force

    $InnerBin = Get-ChildItem -Path $ExtractDir -Recurse -Filter "ffmpeg.exe" |
        Select-Object -First 1 |
        ForEach-Object { $_.Directory.FullName }

    if (-not $InnerBin) {
        throw "Da tai FFmpeg nhung khong tim thay ffmpeg.exe."
    }

    Remove-Item -Recurse -Force $FfmpegDir -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $FfmpegDir | Out-Null
    Copy-Item -Recurse -Force (Join-Path (Split-Path -Parent $InnerBin) "*") $FfmpegDir

    Remove-Item -Recurse -Force $ExtractDir -ErrorAction SilentlyContinue
    Remove-Item -Force $ZipPath -ErrorAction SilentlyContinue

    if (-not ((Test-Path $FfmpegExe) -and (Test-Path $FfprobeExe))) {
        throw "Cai FFmpeg portable khong thanh cong."
    }

    Write-Host "Da cai FFmpeg portable tai: $FfmpegBin"
}

if (-not (Has-Command "python") -and -not (Has-Command "py")) {
    if (Has-Command "winget") {
        Write-Host "Dang cai Python..."
        winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
        Add-PythonToCurrentPath
    } else {
        throw "Khong tim thay Python/py va cung khong co winget de tu cai Python."
    }
}

if (-not (Has-Command "ffmpeg") -or -not (Has-Command "ffprobe")) {
    Install-FFmpegPortable
}

Write-Host "Kiem tra dependency xong."
