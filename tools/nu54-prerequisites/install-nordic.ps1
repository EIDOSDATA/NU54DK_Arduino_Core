<#
.SYNOPSIS
NU54DK Arduino Core가 요구하는 Nordic SDK와 Toolchain을 설치합니다.

.DESCRIPTION
고정 SHA-256의 공식 nRF Util을 내려받고 sdk-manager 1.16.1, NCS v3.4.0 및
Toolchain dcbdc366a1을 사용자 프로필 아래에 설치합니다. 중단된 설치는 incomplete
marker를 남기며 다음 실행에서 같은 명령을 재개합니다.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$PlatformRoot,

    [Parameter()]
    [string]$NcsRoot
)

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $utf8NoBom
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

## @brief UTF-8 BOM 없는 JSON을 임시 file 교체 방식으로 기록합니다.
function Write-AtomicJson {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)]$Value
    )

    $parent = Split-Path -Parent $Path
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    $temporary = "$Path.$([Guid]::NewGuid().ToString('N')).tmp"
    $encoding = [Text.UTF8Encoding]::new($false)
    [IO.File]::WriteAllText(
        $temporary,
        (($Value | ConvertTo-Json -Depth 8) + "`n"),
        $encoding
    )
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}

## @brief PowerShell module 자동 로드에 의존하지 않고 SHA-256을 계산합니다.
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

## @brief 설치 단계와 시각을 재개 가능한 marker에 갱신합니다.
function Set-InstallPhase {
    param([Parameter(Mandatory)][string]$Phase)

    $script:phase = $Phase
    Write-AtomicJson $script:installingPath ([ordered]@{
        schema_version = 1
        status = 'installing'
        phase = $Phase
        platform_root = $script:platformRoot
        ncs_root = $script:ncsRoot
        pins_sha256 = $script:pinsSha256
        updated_at_utc = [DateTime]::UtcNow.ToString('o')
    })
    Add-Content -LiteralPath $script:logPath -Encoding UTF8 -Value "[$([DateTime]::UtcNow.ToString('o'))] phase=$Phase"
    Write-Host "[NU54DK] $Phase" -ForegroundColor Cyan
}

## @brief native process 출력을 log와 console에 남기고 종료 code를 보존합니다.
function Invoke-NativeChecked {
    param(
        [Parameter(Mandatory)][string]$Executable,
        [Parameter(Mandatory)][string[]]$Arguments
    )

    $global:LASTEXITCODE = 0
    & $Executable @Arguments 2>&1 |
        ForEach-Object {
            $outputLine = [string]$_
            Add-Content -LiteralPath $script:logPath -Encoding UTF8 -Value $outputLine
            Write-Host $outputLine
        }
    $exitCode = $global:LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "명령이 종료 code ${exitCode}로 실패했습니다: $Executable $($Arguments -join ' ')"
    }
}

## @brief URL에서 file을 임시 위치로 내려받아 원자적으로 교체합니다.
function Receive-File {
    param(
        [Parameter(Mandatory)][string]$Uri,
        [Parameter(Mandatory)][string]$Destination
    )

    $parent = Split-Path -Parent $Destination
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    $temporary = "$Destination.$([Guid]::NewGuid().ToString('N')).download"
    try {
        $request = @{
            Uri = $Uri
            OutFile = $temporary
            UseBasicParsing = $true
        }
        Invoke-WebRequest @request
        Move-Item -LiteralPath $temporary -Destination $Destination -Force
    } finally {
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
    }
}

## @brief SHA-256 값이 pin과 다르면 변경된 upstream byte를 거부합니다.
function Assert-FileHash {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Expected
    )

    $actual = Get-Sha256 $Path
    if ($actual -ne $Expected.ToLowerInvariant()) {
        throw "SHA-256 불일치: $Path; expected=$Expected actual=$actual. 공식 URL은 unversioned이므로 upstream byte가 변경되었다면 검토 후 pins.json을 명시적으로 갱신하십시오."
    }
}

$mutex = $null
$mutexAcquired = $false
$phase = 'initializing'
$installingPath = $null
$incompletePath = $null
$logPath = $null

try {
    if ($env:OS -ne 'Windows_NT') {
        throw 'M10 자동 prerequisite 설치는 현재 Windows 10/11 x64만 지원합니다.'
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

    $platformRoot = [IO.Path]::GetFullPath($PlatformRoot).TrimEnd('\', '/')
    $ncsRoot = [IO.Path]::GetFullPath($NcsRoot).TrimEnd('\', '/')
    $pinsPath = Join-Path $PSScriptRoot 'pins.json'
    $requirementsPath = Join-Path $PSScriptRoot 'nrfutil-requirements.json'
    $verifyScript = Join-Path $PSScriptRoot 'verify-nordic.ps1'
    foreach ($requiredPackageFile in @($pinsPath, $requirementsPath, $verifyScript)) {
        if (-not (Test-Path -LiteralPath $requiredPackageFile -PathType Leaf)) {
            throw "설치 package file이 없습니다: $requiredPackageFile"
        }
    }
    $pins = Get-Content -LiteralPath $pinsPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ([int]$pins.schema_version -ne 1) {
        throw "지원하지 않는 pin schema입니다: $($pins.schema_version)"
    }
    $pinsSha256 = Get-Sha256 $pinsPath

    $applicationRoot = Join-Path $env:LOCALAPPDATA 'NUCODE\NU54DK_Arduino_Core'
    $stateRoot = if ($env:NUCODE_PREREQUISITE_STATE_ROOT) {
        [IO.Path]::GetFullPath($env:NUCODE_PREREQUISITE_STATE_ROOT)
    } else {
        Join-Path $applicationRoot 'prerequisites'
    }
    $toolsRoot = Join-Path $applicationRoot 'tools'
    $logsRoot = Join-Path $applicationRoot 'logs'
    $installingPath = Join-Path $stateRoot 'installing.json'
    $incompletePath = Join-Path $stateRoot 'incomplete.json'
    $readyPath = Join-Path $stateRoot 'ready.json'
    $nrfutilPath = Join-Path $toolsRoot 'nrfutil.exe'
    New-Item -ItemType Directory -Path $stateRoot, $toolsRoot, $logsRoot, $ncsRoot -Force | Out-Null
    $logPath = Join-Path $logsRoot "prerequisites-$([DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss')).log"
    New-Item -ItemType File -Path $logPath -Force | Out-Null

    $mutexNameSeed = [Text.Encoding]::UTF8.GetBytes($stateRoot.ToLowerInvariant())
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $mutexDigest = ([BitConverter]::ToString($sha.ComputeHash($mutexNameSeed))).Replace('-', '')
    } finally {
        $sha.Dispose()
    }
    $mutex = [Threading.Mutex]::new($false, "Local\NUCODE_NU54_PREREQUISITES_$mutexDigest")
    try {
        $mutexAcquired = $mutex.WaitOne([TimeSpan]::FromMinutes(5))
    } catch [Threading.AbandonedMutexException] {
        $mutexAcquired = $true
    }
    if (-not $mutexAcquired) {
        throw '다른 NU54DK prerequisite 설치가 끝나기를 기다리다 timeout되었습니다.'
    }

    if (Test-Path -LiteralPath $readyPath -PathType Leaf) {
        Set-InstallPhase '기존 완료 marker 검증'
        $verifyArguments = @('-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', $verifyScript, '-PlatformRoot', $platformRoot, '-NcsRoot', $ncsRoot, '-Json')
        & powershell.exe @verifyArguments | Add-Content -LiteralPath $logPath -Encoding UTF8
        if ($LASTEXITCODE -eq 0) {
            Remove-Item -LiteralPath $installingPath, $incompletePath -Force -ErrorAction SilentlyContinue
            Write-Host '[NU54DK] 이미 검증된 Nordic prerequisite를 재사용합니다.' -ForegroundColor Green
            exit 0
        }
        Remove-Item -LiteralPath $readyPath -Force -ErrorAction SilentlyContinue
    }

    Set-InstallPhase '공식 nRF Util byte 준비'
    if (-not (Test-Path -LiteralPath $nrfutilPath -PathType Leaf)) {
        Receive-File ([string]$pins.nrfutil.url) $nrfutilPath
    }
    try {
        Assert-FileHash $nrfutilPath ([string]$pins.nrfutil.sha256)
    } catch {
        Remove-Item -LiteralPath $nrfutilPath -Force -ErrorAction SilentlyContinue
        Receive-File ([string]$pins.nrfutil.url) $nrfutilPath
        Assert-FileHash $nrfutilPath ([string]$pins.nrfutil.sha256)
    }

    $env:NRFUTIL_HOME = Join-Path $applicationRoot 'nrfutil'
    New-Item -ItemType Directory -Path $env:NRFUTIL_HOME -Force | Out-Null

    $nrfutilVersionOutput = (& $nrfutilPath --version 2>&1) -join "`n"
    if ($LASTEXITCODE -ne 0 -or
        $nrfutilVersionOutput -notmatch ("(?im)^nrfutil\s+" + [Regex]::Escape([string]$pins.nrfutil.version) + "(?:\s|\(|$)")) {
        throw "nRF Util core version 출력이 고정 version $($pins.nrfutil.version)과 일치하지 않습니다. 출력 형식 또는 upstream core가 변경되었는지 확인하십시오: $nrfutilVersionOutput"
    }

    Set-InstallPhase 'sdk-manager 1.16.1 설치'
    Invoke-NativeChecked $nrfutilPath @('install', '--set', $requirementsPath)
    $sdkManagerVersionOutput = (& $nrfutilPath sdk-manager --version 2>&1) -join "`n"
    if ($LASTEXITCODE -ne 0 -or
        $sdkManagerVersionOutput -notmatch ("(?<!\d)" + [Regex]::Escape([string]$pins.sdk_manager.version) + "(?!\d)")) {
        throw "sdk-manager version 출력이 고정 version $($pins.sdk_manager.version)과 일치하지 않습니다. 출력 형식 또는 command package를 확인하십시오: $sdkManagerVersionOutput"
    }

    Set-InstallPhase "Toolchain $($pins.toolchain.bundle_id) 설치 또는 재개"
    Invoke-NativeChecked $nrfutilPath @(
        'sdk-manager', 'toolchain', 'install',
        '--toolchain-bundle-id', ([string]$pins.toolchain.bundle_id),
        '--install-dir', $ncsRoot
    )

    Set-InstallPhase "NCS $($pins.ncs.version) 설치 또는 재개"
    Invoke-NativeChecked $nrfutilPath @(
        'sdk-manager', 'sdk', 'install', ([string]$pins.ncs.version),
        '--install-dir', $ncsRoot
    )

    Set-InstallPhase '설치 byte와 revision 최종 검증'
    $verifyOutput = & powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $verifyScript -PlatformRoot $platformRoot -NcsRoot $ncsRoot -SkipReadyMarker -Json 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "설치 검증에 실패했습니다: $($verifyOutput -join ' ')"
    }
    $verified = ($verifyOutput -join "`n") | ConvertFrom-Json
    if ([string]$verified.status -ne 'ready') {
        throw '설치 검증 결과가 ready가 아닙니다.'
    }

    Write-AtomicJson $readyPath ([ordered]@{
        schema_version = 1
        status = 'ready'
        pins_sha256 = $pinsSha256
        nrfutil_path = $nrfutilPath
        nrfutil_sha256 = ([string]$pins.nrfutil.sha256)
        nrfutil_version = ([string]$pins.nrfutil.version)
        sdk_manager_version = ([string]$pins.sdk_manager.version)
        ncs_root = $ncsRoot
        ncs_version = ([string]$pins.ncs.version)
        ncs_revision = ([string]$pins.ncs.revision)
        zephyr_revision = ([string]$pins.zephyr.revision)
        toolchain_root = (Join-Path (Join-Path $ncsRoot 'toolchains') ([string]$pins.toolchain.bundle_id))
        toolchain_bundle_id = ([string]$pins.toolchain.bundle_id)
        completed_at_utc = [DateTime]::UtcNow.ToString('o')
    })

    Set-InstallPhase '완료 marker 재검증'
    $finalOutput = & powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $verifyScript -PlatformRoot $platformRoot -NcsRoot $ncsRoot -Json 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "완료 marker 재검증에 실패했습니다: $($finalOutput -join ' ')"
    }
    Remove-Item -LiteralPath $installingPath, $incompletePath -Force -ErrorAction SilentlyContinue
    Write-Host '[NU54DK] Nordic prerequisite installation PASS.' -ForegroundColor Green
    Write-Host "설치 root: $ncsRoot"
    Write-Host "검증 log : $logPath"
    exit 0
} catch {
    $message = $_.Exception.Message
    if ($incompletePath) {
        try {
            Write-AtomicJson $incompletePath ([ordered]@{
                schema_version = 1
                status = 'incomplete'
                phase = $phase
                error = $message
                platform_root = $platformRoot
                ncs_root = $ncsRoot
                updated_at_utc = [DateTime]::UtcNow.ToString('o')
                log = $logPath
            })
        } catch {
            [Console]::Error.WriteLine("[NU54DK] incomplete marker 기록도 실패했습니다: $($_.Exception.Message)")
        }
    }
    [Console]::Error.WriteLine("[NU54DK] Nordic prerequisite installation failed at '$phase': $message")
    if ($logPath) {
        [Console]::Error.WriteLine("[NU54DK] log: $logPath")
    }
    exit 1
} finally {
    if ($mutexAcquired -and $mutex) {
        $mutex.ReleaseMutex()
    }
    if ($mutex) {
        $mutex.Dispose()
    }
}
