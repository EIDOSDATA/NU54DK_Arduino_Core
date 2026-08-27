<#
.SYNOPSIS
M10 clean Windows Boards Manager 검증을 SSH로 자동 실행합니다.

.DESCRIPTION
저장소를 대상 PC에 clone하지 않고 고정된 target runner와 실행 설정만 전송합니다.
대상은 격리된 Arduino data/downloads/sketchbook/build 경로에서 설치, 빌드,
업로드, upgrade, downgrade, uninstall 및 reinstall을 수행합니다.
#>

[CmdletBinding()]
param(
    [string]$TargetHost = '192.168.1.10',
    [ValidatePattern('^[A-Za-z0-9_.-]{1,64}$')]
    [string]$RemoteUser = 'nu54ci',
    [int]$Port = 22,
    [string]$IdentityFile = "$env:USERPROFILE\.ssh\nu54dk_m10_ed25519",
    [string]$KnownHostsFile = "$env:USERPROFILE\.ssh\known_hosts",
    [string]$IndexUrl = 'https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_preview_index.json',
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$InitialVersion = '0.0.90',
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$LatestVersion = '0.0.91',
    [string]$Fqbn = 'nucode:zephyr:nu54dk',
    [string]$NcsVersion = 'v3.4.0',
    [ValidatePattern('^[0-9a-f]{10}$')]
    [string]$ToolchainBundleId = 'dcbdc366a1',
    [string]$ArduinoCli = 'C:\Program Files\Arduino CLI\arduino-cli.exe',
    [string]$ExpectedArduinoCliVersion = '1.5.2-rc.1',
    [string]$ExpectedArduinoCliCommit = 'fef6e48df',
    [string]$ExpectedArduinoCliSha256 = 'ba1890afcfc08524f76191b5cc801b0779cb25e81a5e6693eb0e26b50a3f3538',
    [string]$RemoteWorkRoot = 'C:\Users\nu54ci\NU54CI\M10',
    [string]$EvidenceRoot,
    [ValidatePattern('^[A-Za-z0-9._-]{1,80}$')]
    [string]$ResumeRunId,
    [int]$SshTimeoutSeconds = 43200,
    [int]$InstallTimeoutSeconds = 10800,
    [int]$BuildTimeoutSeconds = 3600,
    [int]$VerifyTimeoutSeconds = 600,
    [switch]$AllowMissingProbe
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

## @brief UTF-8 BOM 없이 파일을 기록합니다.
function Write-Utf8WithoutBom {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Text
    )

    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Text, $encoding)
}

## @brief 로그에 기록하기 전에 장치 식별자와 자격 증명 형태를 제거합니다.
function Protect-LogText {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Text
    )

    $protected = [regex]::Replace(
        $Text,
        '(?i)\b[0-9a-f]{16,}\b',
        '<redacted-device-id>'
    )
    $protected = [regex]::Replace(
        $protected,
        '(?i)(serial(?:_number| number|number)?\s*[:=]\s*)[^\s,;\]\}]+',
        '$1<redacted-device-id>'
    )
    $protected = [regex]::Replace(
        $protected,
        '(?i)(token|password|secret|authorization)\s*[:=]\s*[^\s,;]+',
        '$1=<redacted>'
    )
    return $protected
}

## @brief native command 인자를 Windows command line 규칙에 맞게 보호합니다.
function Convert-ToNativeArgument {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Value
    )

    if ($Value -notmatch '[\s"]') {
        return $Value
    }
    $escaped = $Value -replace '(\\*)"', '$1$1\"'
    $escaped = $escaped -replace '(\\+)$', '$1$1'
    return '"' + $escaped + '"'
}

## @brief timeout과 종료 코드 allowlist를 적용해 local native command를 실행합니다.
function Invoke-LocalNative {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [Parameter(Mandatory = $true)]
        [string]$Label,
        [int]$TimeoutSeconds = 600,
        [int[]]$AllowedExitCodes = @(0)
    )

    $commandLine = (@($Arguments | ForEach-Object {
        Convert-ToNativeArgument -Value ([string]$_)
    }) -join ' ')
    $commandId = [Guid]::NewGuid().ToString('N')
    $stdoutPath = Join-Path $script:LocalTemporaryRoot ($commandId + '.stdout.txt')
    $stderrPath = Join-Path $script:LocalTemporaryRoot ($commandId + '.stderr.txt')
    $started = [DateTime]::UtcNow
    $process = Start-Process `
        -FilePath $FilePath `
        -ArgumentList $commandLine `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath `
        -WindowStyle Hidden `
        -PassThru
    $completed = $process.WaitForExit($TimeoutSeconds * 1000)
    if (-not $completed) {
        & "$env:SystemRoot\System32\taskkill.exe" /PID $process.Id /T /F 2>&1 | Out-Null
        $process.WaitForExit()
    } else {
        $process.WaitForExit()
    }
    $stdout = ''
    $stderr = ''
    if (Test-Path -LiteralPath $stdoutPath) {
        $stdout = [System.IO.File]::ReadAllText($stdoutPath)
    }
    if (Test-Path -LiteralPath $stderrPath) {
        $stderr = [System.IO.File]::ReadAllText($stderrPath)
    }
    Remove-Item -LiteralPath $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue

    $safeOutput = Protect-LogText -Text (($stdout + [Environment]::NewLine + $stderr).Trim())
    if ($safeOutput) {
        [System.IO.File]::AppendAllText(
            $script:LocalLogPath,
            ("[{0}]`r`n{1}`r`n" -f $Label, $safeOutput),
            (New-Object System.Text.UTF8Encoding($false))
        )
        Write-Host $safeOutput
    }
    if (-not $completed) {
        throw "$Label 작업이 ${TimeoutSeconds}초 후 timeout 되었습니다."
    }
    if ($AllowedExitCodes -notcontains $process.ExitCode) {
        throw "$Label 작업이 종료 코드 $($process.ExitCode)로 실패했습니다."
    }
    return [pscustomobject][ordered]@{
        exit_code = $process.ExitCode
        duration_seconds = [Math]::Round(([DateTime]::UtcNow - $started).TotalSeconds, 3)
        stdout = $stdout
        stderr = $stderr
    }
}

## @brief PowerShell command를 UTF-16LE Base64로 만들어 SSH quoting 영향을 제거합니다.
function Convert-ToEncodedPowerShellCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command
    )

    return [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($Command))
}

## @brief byte 배열의 SHA-256을 소문자 16진 문자열로 계산합니다.
function Get-ByteSha256 {
    param(
        [Parameter(Mandatory = $true)]
        [byte[]]$Bytes
    )

    $algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($algorithm.ComputeHash($Bytes)) -replace '-', '').ToLowerInvariant()
    } finally {
        $algorithm.Dispose()
    }
}

## @brief 공개 index byte와 두 preview archive identity를 실행 전에 고정합니다.
function Get-PublicIndexIdentity {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [Parameter(Mandatory = $true)]
        [string[]]$Versions
    )

    $request = [Net.HttpWebRequest][Net.WebRequest]::Create($Url)
    $request.Method = 'GET'
    $request.Timeout = 120000
    $request.ReadWriteTimeout = 120000
    $request.AllowAutoRedirect = $false
    $response = $request.GetResponse()
    try {
        if ([int]$response.StatusCode -ne 200) {
            throw "package index HTTP 상태가 200이 아닙니다: $([int]$response.StatusCode)"
        }
        $memory = New-Object IO.MemoryStream
        try {
            $response.GetResponseStream().CopyTo($memory)
            $bytes = $memory.ToArray()
        } finally {
            $memory.Dispose()
        }
    } finally {
        $response.Dispose()
    }
    if ($bytes.Length -eq 0) {
        throw 'package index가 비어 있습니다.'
    }
    $utf8 = New-Object Text.UTF8Encoding($false, $true)
    try {
        $document = $utf8.GetString($bytes) | ConvertFrom-Json
    } catch {
        throw "package index JSON 해석에 실패했습니다: $($_.Exception.Message)"
    }
    $packages = @($document.packages)
    if ($packages.Count -ne 1 -or $packages[0].name -ne 'nucode') {
        throw 'package index의 package identity가 nucode 하나가 아닙니다.'
    }
    $platforms = @($packages[0].platforms)
    $archives = [ordered]@{}
    foreach ($version in $Versions) {
        $matches = @($platforms | Where-Object {
            $_.architecture -eq 'zephyr' -and $_.version -eq $version
        })
        if ($matches.Count -ne 1) {
            throw "package index에 zephyr $version record가 정확히 하나가 아닙니다."
        }
        $record = $matches[0]
        $expectedFileName = "nucode-nu54dk-zephyr-$version.zip"
        $expectedReleaseUrl = "https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/download/m10-preview-$version/$expectedFileName"
        if ([string]$record.archiveFileName -ne $expectedFileName -or
            [string]$record.url -ne $expectedReleaseUrl) {
            throw "package index의 $version archive filename 또는 EIDOSDATA release URL이 올바르지 않습니다."
        }
        if ([string]$record.checksum -notmatch '^SHA-256:([0-9a-f]{64})$') {
            throw "package index의 $version checksum이 올바르지 않습니다."
        }
        $archiveSha256 = [string]$Matches[1]
        if ([string]$record.size -notmatch '^[1-9][0-9]*$') {
            throw "package index의 $version size가 올바르지 않습니다."
        }
        $archives[$version] = [ordered]@{
            sha256 = $archiveSha256
            size = [string]$record.size
            file_name = [string]$record.archiveFileName
            url = [string]$record.url
        }
    }
    return [pscustomobject][ordered]@{
        sha256 = Get-ByteSha256 -Bytes $bytes
        archives = $archives
        bytes = $bytes
    }
}

## @brief 고정 release archive byte를 설치 전에 검증하고 manifest commit을 추출합니다.
function Get-PublicArchiveIdentity {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Record,
        [Parameter(Mandatory = $true)]
        [string]$Version,
        [Parameter(Mandatory = $true)]
        [string]$TemporaryRoot
    )

    $request = [Net.HttpWebRequest][Net.WebRequest]::Create([string]$Record.url)
    $request.Method = 'GET'
    $request.Timeout = 300000
    $request.ReadWriteTimeout = 300000
    $request.AllowAutoRedirect = $true
    $request.MaximumAutomaticRedirections = 8
    $response = $request.GetResponse()
    try {
        if ([int]$response.StatusCode -ne 200) {
            throw "archive HTTP 상태가 200이 아닙니다: $([int]$response.StatusCode)"
        }
        $memory = New-Object IO.MemoryStream
        try {
            $response.GetResponseStream().CopyTo($memory)
            $bytes = $memory.ToArray()
        } finally {
            $memory.Dispose()
        }
    } finally {
        $response.Dispose()
    }
    if ([string]$bytes.Length -ne [string]$Record.size) {
        throw "$Version archive size가 package index와 다릅니다."
    }
    $digest = Get-ByteSha256 -Bytes $bytes
    if ($digest -ne [string]$Record.sha256) {
        throw "$Version archive SHA-256이 package index와 다릅니다."
    }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archivePath = Join-Path $TemporaryRoot ([string]$Record.file_name)
    [IO.File]::WriteAllBytes($archivePath, $bytes)
    $archive = [IO.Compression.ZipFile]::OpenRead($archivePath)
    try {
        $manifestEntries = @($archive.Entries | Where-Object {
            $_.FullName -match '^[^/]+/release-manifest\.json$'
        })
        if ($manifestEntries.Count -ne 1) {
            throw "$Version archive에 release-manifest.json이 정확히 하나가 아닙니다."
        }
        $stream = $manifestEntries[0].Open()
        try {
            $reader = [IO.StreamReader]::new(
                $stream,
                [Text.UTF8Encoding]::new($false, $true)
            )
            try {
                $manifestText = $reader.ReadToEnd()
            } finally {
                $reader.Dispose()
            }
        } finally {
            $stream.Dispose()
        }
    } finally {
        $archive.Dispose()
        Remove-Item -LiteralPath $archivePath -Force -ErrorAction SilentlyContinue
    }
    try {
        $manifest = $manifestText | ConvertFrom-Json
    } catch {
        throw "$Version archive release manifest가 유효한 JSON이 아닙니다."
    }
    if ($manifest.schema_version -ne 1 -or
        $manifest.version -ne $Version -or
        $manifest.archive_file_name -ne [string]$Record.file_name -or
        [string]$manifest.core_revision -notmatch '^[0-9a-f]{40}$') {
        throw "$Version archive release manifest identity가 올바르지 않습니다."
    }
    return [pscustomobject][ordered]@{
        core_revision = [string]$manifest.core_revision
        release_manifest_sha256 = Get-ByteSha256 -Bytes ([Text.Encoding]::UTF8.GetBytes($manifestText))
    }
}

if ($env:OS -ne 'Windows_NT') {
    throw '이 실행기는 Windows 개발 PC에서만 사용할 수 있습니다.'
}
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
if ($Port -lt 1 -or $Port -gt 65535) {
    throw 'SSH port 범위가 올바르지 않습니다.'
}
if ($SshTimeoutSeconds -lt 60 -or $InstallTimeoutSeconds -lt 60 -or
    $BuildTimeoutSeconds -lt 60 -or $VerifyTimeoutSeconds -lt 30) {
    throw 'timeout 값이 지나치게 짧습니다.'
}
if ([version]$LatestVersion -le [version]$InitialVersion) {
    throw 'LatestVersion은 InitialVersion보다 높아야 합니다.'
}
if ($Fqbn -ne 'nucode:zephyr:nu54dk') {
    throw '허용되지 않은 FQBN입니다.'
}
if ($ExpectedArduinoCliVersion -notmatch '^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$' -or
    $ExpectedArduinoCliCommit -notmatch '^[0-9a-f]{9}$' -or
    $ExpectedArduinoCliSha256 -notmatch '^[0-9a-f]{64}$') {
    throw 'Arduino CLI expected identity 형식이 올바르지 않습니다.'
}
$indexUri = $null
if (-not [Uri]::TryCreate($IndexUrl, [UriKind]::Absolute, [ref]$indexUri) -or
    $indexUri.Scheme -ne 'https') {
    throw 'IndexUrl은 공개 HTTPS URL이어야 합니다.'
}
if ($indexUri.Host -ne 'raw.githubusercontent.com' -or
    $indexUri.AbsolutePath -notmatch '^/EIDOSDATA/NU54DK_Arduino_Core/' -or
    $indexUri.UserInfo -or $indexUri.Query -or $indexUri.Fragment) {
    throw 'IndexUrl은 EIDOSDATA 공개 raw GitHub 경로여야 하며 자격 증명이나 query를 포함할 수 없습니다.'
}
if ($RemoteWorkRoot -notmatch '^[A-Za-z]:\\[A-Za-z0-9_.\\-]+$' -or
    $RemoteWorkRoot -match '[\r\n'']') {
    throw 'RemoteWorkRoot는 단순한 Windows 절대 경로여야 합니다.'
}
if (-not (Test-Path -LiteralPath $IdentityFile -PathType Leaf)) {
    throw "SSH private key를 찾지 못했습니다: $IdentityFile"
}
if ($IdentityFile.EndsWith('.pub', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'IdentityFile에는 공개키가 아니라 private key 경로가 필요합니다.'
}
if (-not (Test-Path -LiteralPath $KnownHostsFile -PathType Leaf)) {
    throw "known_hosts를 찾지 못했습니다: $KnownHostsFile"
}

$sshCommand = (Get-Command ssh.exe -ErrorAction Stop).Source
$scpCommand = (Get-Command scp.exe -ErrorAction Stop).Source
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$targetRunner = Join-Path $scriptRoot 'run-m10-target.ps1'
if (-not (Test-Path -LiteralPath $targetRunner -PathType Leaf)) {
    throw "target runner를 찾지 못했습니다: $targetRunner"
}
$nonAsciiBytes = [IO.File]::ReadAllBytes($targetRunner) | Where-Object { $_ -gt 127 }
if ($nonAsciiBytes.Count -ne 0) {
    throw 'target runner는 전송 안정성을 위해 ASCII여야 합니다.'
}

$runId = $ResumeRunId
if (-not $runId) {
    $runId = 'm10-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
}
if (-not $EvidenceRoot) {
    $repositoryRoot = (Resolve-Path (Join-Path $scriptRoot '..\..\..')).Path
    $EvidenceRoot = Join-Path $repositoryRoot 'build\m10\remote'
}
$localRunRoot = Join-Path $EvidenceRoot $runId
$script:LocalTemporaryRoot = Join-Path $localRunRoot 'tmp'
$script:LocalLogPath = Join-Path $localRunRoot 'orchestrator.log'
New-Item -ItemType Directory -Path $script:LocalTemporaryRoot -Force | Out-Null
Write-Utf8WithoutBom -Path $script:LocalLogPath -Text ''
$indexIdentity = Get-PublicIndexIdentity `
    -Url $IndexUrl `
    -Versions @($InitialVersion, $LatestVersion)
foreach ($version in @($InitialVersion, $LatestVersion)) {
    $releaseIdentity = Get-PublicArchiveIdentity `
        -Record $indexIdentity.archives[$version] `
        -Version $version `
        -TemporaryRoot $script:LocalTemporaryRoot
    $indexIdentity.archives[$version]['core_revision'] = $releaseIdentity.core_revision
    $indexIdentity.archives[$version]['release_manifest_sha256'] = $releaseIdentity.release_manifest_sha256
}
$localIndexSnapshot = Join-Path $localRunRoot 'package-index.snapshot.json'
[IO.File]::WriteAllBytes($localIndexSnapshot, $indexIdentity.bytes)
$targetRunnerSha256 = (Get-FileHash -LiteralPath $targetRunner -Algorithm SHA256).Hash.ToLowerInvariant()

$remoteStagingWindows = "$RemoteWorkRoot\staging\$runId"
$remoteStagingScp = ($remoteStagingWindows -replace '\\', '/')
$remoteRunWindows = "$RemoteWorkRoot\runs\$runId"
$remoteRunScp = ($remoteRunWindows -replace '\\', '/')
$remoteRunnerPath = "$remoteStagingWindows\run-m10-target.ps1"
$remoteConfigPath = "$remoteStagingWindows\config.json"
$localConfigPath = Join-Path $script:LocalTemporaryRoot 'config.json'

$configuration = [ordered]@{
    schema_version = 1
    run_id = $runId
    index_url = $IndexUrl
    initial_version = $InitialVersion
    latest_version = $LatestVersion
    fqbn = $Fqbn
    ncs_version = $NcsVersion
    toolchain_bundle_id = $ToolchainBundleId
    arduino_cli = $ArduinoCli
    arduino_cli_version = $ExpectedArduinoCliVersion
    arduino_cli_commit = $ExpectedArduinoCliCommit
    arduino_cli_sha256 = $ExpectedArduinoCliSha256
    target_runner_sha256 = $targetRunnerSha256
    index_sha256 = $indexIdentity.sha256
    archives = $indexIdentity.archives
    work_root = $RemoteWorkRoot
    install_timeout_seconds = $InstallTimeoutSeconds
    build_timeout_seconds = $BuildTimeoutSeconds
    verify_timeout_seconds = $VerifyTimeoutSeconds
    require_probe = (-not $AllowMissingProbe.IsPresent)
}
Write-Utf8WithoutBom `
    -Path $localConfigPath `
    -Text (($configuration | ConvertTo-Json -Depth 10) + [Environment]::NewLine)

$sshTarget = "$RemoteUser@$TargetHost"
$sshOptions = @(
    '-i', $IdentityFile,
    '-p', [string]$Port,
    '-o', 'BatchMode=yes',
    '-o', 'IdentitiesOnly=yes',
    '-o', 'StrictHostKeyChecking=yes',
    '-o', ("UserKnownHostsFile={0}" -f $KnownHostsFile),
    '-o', 'ConnectTimeout=15',
    '-o', 'ServerAliveInterval=30',
    '-o', 'ServerAliveCountMax=4'
)
$scpOptions = @(
    '-i', $IdentityFile,
    '-P', [string]$Port,
    '-o', 'BatchMode=yes',
    '-o', 'IdentitiesOnly=yes',
    '-o', 'StrictHostKeyChecking=yes',
    '-o', ("UserKnownHostsFile={0}" -f $KnownHostsFile),
    '-o', 'ConnectTimeout=15'
)

$remoteSetup = "New-Item -ItemType Directory -Path '$remoteStagingWindows' -Force | Out-Null"
$encodedSetup = Convert-ToEncodedPowerShellCommand -Command $remoteSetup
Invoke-LocalNative `
    -FilePath $sshCommand `
    -Arguments ($sshOptions + @(
        $sshTarget,
        'powershell.exe',
        '-NoProfile',
        '-NonInteractive',
        '-ExecutionPolicy',
        'Bypass',
        '-EncodedCommand',
        $encodedSetup
    )) `
    -Label 'remote-staging-create' `
    -TimeoutSeconds 120 | Out-Null

Invoke-LocalNative `
    -FilePath $scpCommand `
    -Arguments ($scpOptions + @(
        $targetRunner,
        ("{0}:{1}/run-m10-target.ps1" -f $sshTarget, $remoteStagingScp)
    )) `
    -Label 'target-runner-upload' `
    -TimeoutSeconds 180 | Out-Null
Invoke-LocalNative `
    -FilePath $scpCommand `
    -Arguments ($scpOptions + @(
        $localConfigPath,
        ("{0}:{1}/config.json" -f $sshTarget, $remoteStagingScp)
    )) `
    -Label 'target-config-upload' `
    -TimeoutSeconds 180 | Out-Null

$remoteRunCommand = "& '$remoteRunnerPath' -ConfigPath '$remoteConfigPath'"
$encodedRun = Convert-ToEncodedPowerShellCommand -Command $remoteRunCommand
$remoteResult = $null
$downloadFailure = $null
try {
    $remoteResult = Invoke-LocalNative `
        -FilePath $sshCommand `
        -Arguments ($sshOptions + @(
            $sshTarget,
            'powershell.exe',
            '-NoProfile',
            '-NonInteractive',
            '-ExecutionPolicy',
            'Bypass',
            '-EncodedCommand',
            $encodedRun
        )) `
        -Label 'm10-target-run' `
        -TimeoutSeconds $SshTimeoutSeconds `
        -AllowedExitCodes @(0, 1)
} finally {
    foreach ($artifactName in @('evidence.json', 'state.json')) {
        try {
            Invoke-LocalNative `
                -FilePath $scpCommand `
                -Arguments ($scpOptions + @(
                    ("{0}:{1}/{2}" -f $sshTarget, $remoteRunScp, $artifactName),
                    (Join-Path $localRunRoot $artifactName)
                )) `
                -Label ("download-{0}" -f $artifactName) `
                -TimeoutSeconds 180 | Out-Null
        } catch {
            $downloadFailure = $_.Exception.Message
        }
    }
    try {
        Invoke-LocalNative `
            -FilePath $scpCommand `
            -Arguments ($scpOptions + @(
                ("{0}:{1}/logs/runner.log" -f $sshTarget, $remoteRunScp),
                (Join-Path $localRunRoot 'runner.log')
            )) `
            -Label 'download-runner-log' `
            -TimeoutSeconds 180 | Out-Null
    } catch {
        $downloadFailure = $_.Exception.Message
    }
}

$targetEvidencePath = Join-Path $localRunRoot 'evidence.json'
if ($downloadFailure -or -not (Test-Path -LiteralPath $targetEvidencePath -PathType Leaf)) {
    throw "원격 evidence bundle 회수에 실패했습니다: $downloadFailure"
}
$targetEvidence = Get-Content -LiteralPath $targetEvidencePath -Raw -Encoding UTF8 | ConvertFrom-Json
$orchestratorEvidence = [ordered]@{
    schema_version = 1
    milestone = 'M10'
    run_id = $runId
    status = [string]$targetEvidence.status
    target = [ordered]@{
        host = $TargetHost
        port = $Port
        user = $RemoteUser
    }
    public_index_url = $IndexUrl
    public_index_sha256 = $indexIdentity.sha256
    archives = $indexIdentity.archives
    target_runner_sha256 = $targetRunnerSha256
    expected_arduino_cli = [ordered]@{
        version = $ExpectedArduinoCliVersion
        commit = $ExpectedArduinoCliCommit
        sha256 = $ExpectedArduinoCliSha256
    }
    remote_exit_code = if ($null -ne $remoteResult) { $remoteResult.exit_code } else { $null }
    target_evidence_sha256 = (Get-FileHash -LiteralPath $targetEvidencePath -Algorithm SHA256).Hash.ToLowerInvariant()
    completed_at_utc = [DateTime]::UtcNow.ToString('o')
}
$orchestratorEvidencePath = Join-Path $localRunRoot 'orchestrator.json'
Write-Utf8WithoutBom `
    -Path $orchestratorEvidencePath `
    -Text (($orchestratorEvidence | ConvertTo-Json -Depth 10) + [Environment]::NewLine)

Remove-Item -LiteralPath $script:LocalTemporaryRoot -Recurse -Force -ErrorAction SilentlyContinue
if ($remoteResult.exit_code -ne 0 -or $targetEvidence.status -ne 'passed') {
    throw "M10 clean Windows 검증이 실패했습니다. evidence: $targetEvidencePath"
}
Write-Host "M10 clean Windows 검증 PASS: $targetEvidencePath" -ForegroundColor Green
