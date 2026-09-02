<#
.SYNOPSIS
NU54DK Arduino Core가 사용하는 Nordic SDK와 Toolchain 설치를 검증합니다.

.DESCRIPTION
고정 pin, 설치 완료 marker, nRF Connect SDK와 Zephyr revision, Toolchain bundle 및
nRF Util byte hash를 검증합니다. 시스템 PATH나 사용자 환경 변수는 변경하지 않습니다.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$PlatformRoot,

    [Parameter()]
    [string]$NcsRoot,

    [Parameter()]
    [switch]$Json,

    [Parameter(DontShow)]
    [switch]$SkipReadyMarker
)

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $utf8NoBom
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

## @brief 경로를 비교 가능한 완전한 절대 경로로 변환합니다.
function Resolve-FullPath {
    param([Parameter(Mandatory)][string]$Path)

    return [IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
}

## @brief JSON file을 object로 읽고 손상된 입력을 명시적으로 거부합니다.
function Read-JsonDocument {
    param([Parameter(Mandatory)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "필수 JSON file이 없습니다: $Path"
    }
    try {
        return Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        throw "JSON file을 읽지 못했습니다: $Path; 원인: $($_.Exception.Message)"
    }
}

## @brief SHA-256 값을 소문자 64자리 문자열로 계산합니다.
function Get-Sha256 {
    param([Parameter(Mandatory)][string]$Path)

    $stream = [IO.File]::OpenRead($Path)
    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($sha256.ComputeHash($stream))).Replace('-', '').ToLowerInvariant()
    } finally {
        $sha256.Dispose()
        $stream.Dispose()
    }
}

## @brief Toolchain에 포함된 Git으로 요청 repository의 정확한 HEAD를 읽습니다.
function Get-RepositoryRevision {
    param(
        [Parameter(Mandatory)][string]$GitExecutable,
        [Parameter(Mandatory)][string]$Repository
    )

    $output = & $GitExecutable -C $Repository rev-parse HEAD 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Git revision을 읽지 못했습니다: $Repository; $($output -join ' ')"
    }
    $revision = (($output | Select-Object -Last 1) -as [string]).Trim().ToLowerInvariant()
    if ($revision -notmatch '^[0-9a-f]{40}$') {
        throw "Git revision 형식이 잘못되었습니다: $Repository; $revision"
    }
    return $revision
}

## @brief 두 값을 대소문자 구분 없이 비교하고 다르면 설치를 거부합니다.
function Assert-Equal {
    param(
        [Parameter(Mandatory)][string]$Name,
        [AllowEmptyString()][string]$Actual,
        [AllowEmptyString()][string]$Expected
    )

    if (-not [string]::Equals($Actual, $Expected, [StringComparison]::OrdinalIgnoreCase)) {
        throw "$Name 값이 고정 계약과 다릅니다. expected=$Expected actual=$Actual"
    }
}

try {
    if ($env:OS -ne 'Windows_NT') {
        throw 'M10 prerequisite 검증은 현재 Windows 10/11 x64만 지원합니다.'
    }
    if (-not $env:LOCALAPPDATA -or -not $env:USERPROFILE) {
        throw 'LOCALAPPDATA 또는 USERPROFILE 환경 변수가 없습니다.'
    }

    if (-not $PlatformRoot) {
        $PlatformRoot = Join-Path $PSScriptRoot '..\..'
    }
    if (-not $NcsRoot) {
        $NcsRoot = Join-Path $env:USERPROFILE 'ncs'
    }

    $PlatformRoot = Resolve-FullPath $PlatformRoot
    $NcsRoot = Resolve-FullPath $NcsRoot
    $pinsPath = Join-Path $PSScriptRoot 'pins.json'
    $pins = Read-JsonDocument $pinsPath
    if ([int]$pins.schema_version -ne 1) {
        throw "지원하지 않는 pin schema입니다: $($pins.schema_version)"
    }
    $pinsSha256 = Get-Sha256 $pinsPath

    $applicationRoot = Join-Path $env:LOCALAPPDATA 'NUCODE\NU54DK_Arduino_Core'
    $stateRoot = if ($env:NUCODE_PREREQUISITE_STATE_ROOT) {
        Resolve-FullPath $env:NUCODE_PREREQUISITE_STATE_ROOT
    } else {
        Join-Path $applicationRoot 'prerequisites'
    }
    $readyPath = Join-Path $stateRoot 'ready.json'
    $nrfutilPath = Join-Path $applicationRoot 'tools\nrfutil.exe'
    $env:NRFUTIL_HOME = Join-Path $applicationRoot 'nrfutil'
    $sdkRoot = Join-Path $NcsRoot ([string]$pins.ncs.version)
    $toolchainRoot = Join-Path (Join-Path $NcsRoot 'toolchains') ([string]$pins.toolchain.bundle_id)
    $toolchainManifestPath = Join-Path $toolchainRoot 'manifest.json'

    $requiredFiles = @(
        $nrfutilPath,
        (Join-Path $sdkRoot 'nrf\west.yml'),
        (Join-Path $sdkRoot 'zephyr\CMakeLists.txt'),
        (Join-Path $toolchainRoot 'environment.json'),
        $toolchainManifestPath,
        (Join-Path $toolchainRoot 'opt\bin\python.exe'),
        (Join-Path $toolchainRoot 'opt\bin\Scripts\west.exe'),
        (Join-Path $toolchainRoot 'opt\zephyr-sdk\gnu\arm-zephyr-eabi\bin\arm-zephyr-eabi-g++.exe'),
        (Join-Path $toolchainRoot 'bin\git.exe')
    )
    foreach ($requiredFile in $requiredFiles) {
        if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
            throw "Nordic 설치가 불완전합니다. 필수 file이 없습니다: $requiredFile"
        }
    }

    $toolchainManifest = Read-JsonDocument $toolchainManifestPath
    Assert-Equal 'Toolchain manifest bundle_id' ([string]$toolchainManifest.bundle_id) ([string]$pins.toolchain.bundle_id)

    Assert-Equal 'nRF Util SHA-256' (Get-Sha256 $nrfutilPath) ([string]$pins.nrfutil.sha256)
    $nrfutilVersionOutput = (& $nrfutilPath --version 2>&1) -join "`n"
    if ($LASTEXITCODE -ne 0 -or
        $nrfutilVersionOutput -notmatch ("(?im)^nrfutil\s+" + [Regex]::Escape([string]$pins.nrfutil.version) + "(?:\s|\(|$)")) {
        throw "nRF Util core version 출력이 고정 version $($pins.nrfutil.version)과 일치하지 않습니다. 출력 형식 또는 upstream core가 변경되었는지 확인하십시오: $nrfutilVersionOutput"
    }
    $sdkManagerVersionOutput = (& $nrfutilPath sdk-manager --version 2>&1) -join "`n"
    if ($LASTEXITCODE -ne 0 -or
        $sdkManagerVersionOutput -notmatch ("(?<!\d)" + [Regex]::Escape([string]$pins.sdk_manager.version) + "(?!\d)")) {
        throw "sdk-manager version 출력이 고정 version $($pins.sdk_manager.version)과 일치하지 않습니다. 출력 형식 또는 command package를 확인하십시오: $sdkManagerVersionOutput"
    }
    $gitExecutable = Join-Path $toolchainRoot 'bin\git.exe'
    $ncsRevision = Get-RepositoryRevision $gitExecutable (Join-Path $sdkRoot 'nrf')
    $zephyrRevision = Get-RepositoryRevision $gitExecutable (Join-Path $sdkRoot 'zephyr')
    Assert-Equal 'NCS revision' $ncsRevision ([string]$pins.ncs.revision)
    Assert-Equal 'Zephyr revision' $zephyrRevision ([string]$pins.zephyr.revision)

    $ready = $null
    if (-not $SkipReadyMarker) {
        $ready = Read-JsonDocument $readyPath
        if ([int]$ready.schema_version -ne 1 -or [string]$ready.status -ne 'ready') {
            throw "설치 완료 marker 상태가 잘못되었습니다: $readyPath"
        }
        Assert-Equal 'marker pin SHA-256' ([string]$ready.pins_sha256) $pinsSha256
        Assert-Equal 'marker NCS root' (Resolve-FullPath ([string]$ready.ncs_root)) $NcsRoot
        Assert-Equal 'marker NCS version' ([string]$ready.ncs_version) ([string]$pins.ncs.version)
        Assert-Equal 'marker NCS revision' ([string]$ready.ncs_revision) $ncsRevision
        Assert-Equal 'marker Zephyr revision' ([string]$ready.zephyr_revision) $zephyrRevision
        Assert-Equal 'marker Toolchain bundle' ([string]$ready.toolchain_bundle_id) ([string]$pins.toolchain.bundle_id)
        Assert-Equal 'marker Toolchain root' (Resolve-FullPath ([string]$ready.toolchain_root)) $toolchainRoot
        Assert-Equal 'marker nRF Util SHA-256' ([string]$ready.nrfutil_sha256) ([string]$pins.nrfutil.sha256)
        Assert-Equal 'marker nRF Util path' (Resolve-FullPath ([string]$ready.nrfutil_path)) (Resolve-FullPath $nrfutilPath)
        Assert-Equal 'marker nRF Util version' ([string]$ready.nrfutil_version) ([string]$pins.nrfutil.version)
        Assert-Equal 'marker sdk-manager version' ([string]$ready.sdk_manager_version) ([string]$pins.sdk_manager.version)
    }

    $result = [ordered]@{
        schema_version = 1
        status = 'ready'
        platform_root = $PlatformRoot
        pins_sha256 = $pinsSha256
        nrfutil_path = $nrfutilPath
        nrfutil_sha256 = ([string]$pins.nrfutil.sha256)
        nrfutil_version = ([string]$pins.nrfutil.version)
        sdk_manager_version = ([string]$pins.sdk_manager.version)
        ncs_root = $NcsRoot
        ncs_version = ([string]$pins.ncs.version)
        ncs_revision = $ncsRevision
        zephyr_revision = $zephyrRevision
        toolchain_root = $toolchainRoot
        toolchain_bundle_id = ([string]$pins.toolchain.bundle_id)
        ready_marker = $readyPath
    }
    if ($Json) {
        [Console]::Out.WriteLine(($result | ConvertTo-Json -Depth 4 -Compress))
    } else {
        Write-Host '[NU54DK] Nordic prerequisite verification PASS.' -ForegroundColor Green
        Write-Host "NCS       : $sdkRoot"
        Write-Host "Toolchain : $toolchainRoot"
        Write-Host "Marker    : $readyPath"
    }
    exit 0
} catch {
    [Console]::Error.WriteLine("[NU54DK] Nordic prerequisite verification failed: $($_.Exception.Message)")
    exit 1
}
