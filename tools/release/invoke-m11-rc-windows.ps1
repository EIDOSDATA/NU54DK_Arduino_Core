<#
.SYNOPSIS
M11 RC 고정 package gate를 clean Windows 대상에서 SSH로 실행합니다.

.DESCRIPTION
로컬 RC plan과 모든 package artifact byte를 먼저 검증한 뒤, 대상 PC에서 공개
EIDOSDATA 저장소의 exact RC commit과 보드 submodule을 checkout합니다. M10이 만든
ready.json의 고정 Toolchain Python/Git과 SHA-256이 고정된 Arduino CLI만 사용해
Arduino package, Zephyr target, pyOCD+UART HIL gate를 순서대로 실행하고 evidence를
로컬로 회수합니다. Git 자격 증명이나 장치 식별자는 입력 또는 결과에 저장하지 않습니다.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ReleaseRoot,
    [string]$TargetHost = '192.168.1.10',
    [ValidatePattern('^[A-Za-z0-9_.-]{1,64}$')]
    [string]$RemoteUser = 'nu54ci',
    [int]$Port = 22,
    [string]$IdentityFile = "$env:USERPROFILE\.ssh\nu54dk_m10_ed25519",
    [string]$KnownHostsFile = "$env:USERPROFILE\.ssh\known_hosts",
    [string]$RemoteWorkRoot = 'C:\Users\nu54ci\NU54CI\M11',
    [string]$ArduinoCli = 'C:\Program Files\Arduino CLI\arduino-cli.exe',
    [string]$SerialPort = 'auto',
    [string]$EvidenceRoot,
    [ValidatePattern('^[A-Za-z0-9._-]{1,80}$')]
    [string]$RunId,
    [string]$LocalPython = 'python',
    [int]$SshTimeoutSeconds = 21600,
    [int]$ArduinoGateTimeoutSeconds = 7200,
    [int]$ZephyrGateTimeoutSeconds = 7200,
    [int]$HilGateTimeoutSeconds = 1800
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:RepositoryUrl = 'https://github.com/EIDOSDATA/NU54DK_Arduino_Core.git'
$script:ExpectedVersion = '0.1.0-rc.1'
$script:ExpectedToolchainBundleId = 'dcbdc366a1'
$script:ExpectedNcsVersion = 'v3.4.0'
$script:ExpectedArduinoCliSha256 = 'ba1890afcfc08524f76191b5cc801b0779cb25e81a5e6693eb0e26b50a3f3538'
$script:RemoteGateIds = @(
    'arduino_cli_fixed_package',
    'zephyr_regression',
    'hil_rc_pyocd'
)
$script:ExpectedArtifactKeys = @(
    'archive',
    'checksums',
    'index',
    'licenses',
    'manifest',
    'notices',
    'sbom'
)
$script:ExpectedResultFiles = @(
    'arduino_cli_fixed_package.evidence.json',
    'arduino_cli_fixed_package.evidence.log',
    'zephyr_regression.evidence.json',
    'zephyr_regression.evidence.log',
    'hil_rc_pyocd.evidence.json',
    'hil_rc_pyocd.evidence.log',
    'hil_rc_pyocd.evidence.result.json'
)
$script:SensitiveLogValues = @()

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
    [IO.File]::WriteAllText($Path, $Text, $encoding)
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

## @brief 파일을 streaming 방식으로 읽어 SHA-256을 계산합니다.
function Get-FileSha256 {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $stream = [IO.File]::OpenRead($Path)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($algorithm.ComputeHash($stream)) -replace '-', '').ToLowerInvariant()
    } finally {
        $algorithm.Dispose()
        $stream.Dispose()
    }
}

## @brief 로그에 기록하기 전에 endpoint, 장치 식별자와 자격 증명 형태를 제거합니다.
function Protect-LogText {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Text
    )

    $protected = $Text
    $sensitiveVariable = Get-Variable -Name SensitiveLogValues -Scope Script -ErrorAction SilentlyContinue
    if ($sensitiveVariable) {
        foreach ($value in @($sensitiveVariable.Value)) {
            if ([string]$value) {
                $protected = [regex]::Replace(
                    $protected,
                    [regex]::Escape([string]$value),
                    '<redacted-endpoint>',
                    [Text.RegularExpressions.RegexOptions]::IgnoreCase
                )
            }
        }
    }
    $protected = [regex]::Replace(
        $protected,
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
        '(?i)\bCOM[1-9][0-9]{0,2}\b',
        '<redacted-device-port>'
    )
    $protected = [regex]::Replace(
        $protected,
        '(?i)(token|password|secret|authorization|bearer)\s*[:= ]\s*[^\s,;]+',
        '$1=<redacted>'
    )
    $protected = [regex]::Replace(
        $protected,
        '(?i)\b(?:github_pat_[A-Za-z0-9_]+|gh[pousr]_[A-Za-z0-9]+)\b',
        '<redacted>'
    )
    $protected = [regex]::Replace(
        $protected,
        '-----BEGIN [^-]*PRIVATE KEY-----',
        '<redacted-private-key>'
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

## @brief 임시 출력 파일의 마지막 부분만 메모리로 읽습니다.
function Read-BoundedTextTail {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [Text.Encoding]$Encoding,
        [int]$MaximumBytes = 1048576
    )

    if ($MaximumBytes -lt 1) {
        throw '출력 tail 제한은 1 byte 이상이어야 합니다.'
    }
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return ''
    }

    $stream = [IO.FileStream]::new(
        $Path,
        [IO.FileMode]::Open,
        [IO.FileAccess]::Read,
        [IO.FileShare]::ReadWrite
    )
    try {
        $offset = [int64]0
        if ($stream.Length -gt $MaximumBytes) {
            $offset = $stream.Length - [int64]$MaximumBytes
        }
        [void]$stream.Seek($offset, [IO.SeekOrigin]::Begin)
        $count = [int]($stream.Length - $offset)
        $bytes = [byte[]]::new($count)
        $read = 0
        while ($read -lt $count) {
            $current = $stream.Read($bytes, $read, $count - $read)
            if ($current -eq 0) {
                break
            }
            $read += $current
        }
        $text = $Encoding.GetString($bytes, 0, $read)
    } finally {
        $stream.Dispose()
    }
    if ($offset -gt 0) {
        return "[output truncated to last $MaximumBytes bytes]`r`n$text"
    }
    return $text
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

    if ($TimeoutSeconds -lt 1) {
        throw "$Label timeout은 1초 이상이어야 합니다."
    }
    $commandLine = (@($Arguments | ForEach-Object {
        Convert-ToNativeArgument -Value ([string]$_)
    }) -join ' ')
    $started = [DateTime]::UtcNow
    $commandId = [Guid]::NewGuid().ToString('N')
    $stdoutPath = Join-Path $script:LocalTemporaryRoot ($commandId + '.stdout.log')
    $stderrPath = Join-Path $script:LocalTemporaryRoot ($commandId + '.stderr.log')
    $startInfo = New-Object Diagnostics.ProcessStartInfo
    $startInfo.FileName = $FilePath
    $startInfo.Arguments = $commandLine
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $startInfo
    $stdoutStream = $null
    $stderrStream = $null
    $stdoutTask = $null
    $stderrTask = $null
    $completed = $false
    $exitCode = $null
    $stdoutEncoding = [Console]::OutputEncoding
    $stderrEncoding = [Console]::OutputEncoding
    try {
        if (-not $process.Start()) {
            throw "$Label process를 시작하지 못했습니다."
        }
        $stdoutEncoding = $process.StandardOutput.CurrentEncoding
        $stderrEncoding = $process.StandardError.CurrentEncoding
        $stdoutStream = [IO.FileStream]::new(
            $stdoutPath,
            [IO.FileMode]::CreateNew,
            [IO.FileAccess]::Write,
            [IO.FileShare]::Read
        )
        $stderrStream = [IO.FileStream]::new(
            $stderrPath,
            [IO.FileMode]::CreateNew,
            [IO.FileAccess]::Write,
            [IO.FileShare]::Read
        )
        $stdoutTask = $process.StandardOutput.BaseStream.CopyToAsync($stdoutStream)
        $stderrTask = $process.StandardError.BaseStream.CopyToAsync($stderrStream)
        $completed = $process.WaitForExit($TimeoutSeconds * 1000)
        if (-not $completed) {
            & "$env:SystemRoot\System32\taskkill.exe" /PID $process.Id /T /F 2>&1 | Out-Null
        }
        $process.WaitForExit()
        [void]$stdoutTask.GetAwaiter().GetResult()
        [void]$stderrTask.GetAwaiter().GetResult()
        $stdoutStream.Flush($true)
        $stderrStream.Flush($true)
        $exitCode = $process.ExitCode
    } finally {
        if ($stdoutStream) {
            $stdoutStream.Dispose()
        }
        if ($stderrStream) {
            $stderrStream.Dispose()
        }
        $process.Dispose()
    }

    $stdout = Read-BoundedTextTail -Path $stdoutPath -Encoding $stdoutEncoding
    $stderr = Read-BoundedTextTail -Path $stderrPath -Encoding $stderrEncoding
    Remove-Item -LiteralPath $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue
    $safeOutput = Protect-LogText -Text (($stdout + [Environment]::NewLine + $stderr).Trim())
    if ($safeOutput) {
        [IO.File]::AppendAllText(
            $script:LocalLogPath,
            ("[{0}]`r`n{1}`r`n" -f $Label, $safeOutput),
            (New-Object Text.UTF8Encoding($false))
        )
        Write-Host $safeOutput
    }
    if (-not $completed) {
        throw "$Label 작업이 ${TimeoutSeconds}초 후 timeout 되었습니다."
    }
    if ($AllowedExitCodes -notcontains $exitCode) {
        throw "$Label 작업이 종료 코드 $exitCode로 실패했습니다."
    }
    return [pscustomobject][ordered]@{
        exit_code = $exitCode
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

## @brief symlink와 reparse point가 아닌 일반 파일만 허용합니다.
function Assert-RegularFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Label 파일이 없습니다: $Path"
    }
    $item = Get-Item -LiteralPath $Path -Force
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "$Label 파일은 symlink 또는 reparse point일 수 없습니다: $Path"
    }
}

## @brief plan artifact가 같은 directory의 고정 byte인지 검증합니다.
function Get-ReleaseBundle {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PlanPath,
        [Parameter(Mandatory = $true)]
        [string]$Root
    )

    try {
        $plan = Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        throw "M11 plan JSON을 읽지 못했습니다: $($_.Exception.Message)"
    }
    if ($plan.schema_version -ne 1 -or
        $plan.milestone -ne 'M11' -or
        $plan.kind -ne 'release-candidate-plan' -or
        $plan.version -ne $script:ExpectedVersion -or
        $plan.release_tag -ne 'v0.1.0-rc.1' -or
        $plan.source_repository -ne 'https://github.com/EIDOSDATA/NU54DK_Arduino_Core' -or
        [string]$plan.core_revision -notmatch '^[0-9a-f]{40}$' -or
        [string]$plan.board_revision -notmatch '^[0-9a-f]{40}$' -or
        [string]$plan.runtime_payload_sha256 -notmatch '^[0-9a-f]{64}$') {
        throw 'M11 plan의 release/source identity가 고정 계약과 다릅니다.'
    }
    $properties = @($plan.artifacts.PSObject.Properties)
    $names = @($properties | ForEach-Object { [string]$_.Name } | Sort-Object)
    $expectedNames = @($script:ExpectedArtifactKeys | Sort-Object)
    if (($names -join "`n") -ne ($expectedNames -join "`n")) {
        throw 'M11 plan artifact key 집합이 고정 계약과 다릅니다.'
    }

    $rootPath = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    $seenNames = @{}
    $files = New-Object Collections.Generic.List[string]
    $files.Add([IO.Path]::GetFullPath($PlanPath))
    foreach ($property in $properties) {
        $record = $property.Value
        $fileName = [string]$record.file_name
        if ($fileName -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,180}$' -or
            [IO.Path]::GetFileName($fileName) -ne $fileName -or
            $seenNames.ContainsKey($fileName.ToLowerInvariant()) -or
            [string]$record.sha256 -notmatch '^[0-9a-f]{64}$' -or
            [string]$record.size -notmatch '^[1-9][0-9]*$') {
            throw "M11 plan artifact record가 유효하지 않습니다: $($property.Name)"
        }
        $seenNames[$fileName.ToLowerInvariant()] = $true
        $path = [IO.Path]::GetFullPath((Join-Path $rootPath $fileName))
        if ([IO.Path]::GetDirectoryName($path).TrimEnd('\') -ne $rootPath) {
            throw "M11 artifact가 ReleaseRoot 밖에 있습니다: $fileName"
        }
        Assert-RegularFile -Path $path -Label "M11 artifact $($property.Name)"
        if ([string](Get-Item -LiteralPath $path).Length -ne [string]$record.size -or
            (Get-FileSha256 -Path $path) -ne [string]$record.sha256) {
            throw "M11 artifact byte identity가 plan과 다릅니다: $fileName"
        }
        $files.Add($path)
    }
    return [pscustomobject][ordered]@{
        plan = $plan
        files = @($files)
        plan_sha256 = Get-FileSha256 -Path $PlanPath
    }
}

## @brief 실행 결과를 endpoint 원문 없이 JSON evidence로 기록합니다.
function Write-OrchestratorResult {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet('passed', 'failed')]
        [string]$Status,
        [string]$Failure,
        [object[]]$GateRecords = @()
    )

    $result = [ordered]@{
        schema_version = 1
        milestone = 'M11'
        evidence_type = 'remote-gate-orchestrator'
        status = $Status
        run_id = $script:CurrentRunId
        release = [ordered]@{
            version = $script:Plan.version
            core_revision = $script:Plan.core_revision
            board_revision = $script:Plan.board_revision
            runtime_payload_sha256 = $script:Plan.runtime_payload_sha256
            plan_sha256 = $script:PlanSha256
        }
        target = [ordered]@{
            endpoint_sha256 = Get-ByteSha256 -Bytes ([Text.Encoding]::UTF8.GetBytes($script:SshTarget))
            port = $Port
            host_key_policy = 'strict-pinned-known-hosts'
            public_repository_clone = $script:RepositoryUrl
        }
        ssh = [ordered]@{
            batch_mode = $true
            identities_only = $true
            strict_host_key_checking = $true
            identity_file_sha256 = Get-FileSha256 -Path $IdentityFile
            known_hosts_sha256 = Get-FileSha256 -Path $KnownHostsFile
        }
        gates = @($GateRecords)
        failure = if ($Failure) { Protect-LogText -Text $Failure } else { $null }
        redaction = [ordered]@{
            credentials = $true
            device_identifiers = $true
            target_endpoint = $true
        }
        completed_at_utc = [DateTime]::UtcNow.ToString('o')
    }
    Write-Utf8WithoutBom `
        -Path $script:OrchestratorResultPath `
        -Text (($result | ConvertTo-Json -Depth 10) + [Environment]::NewLine)
}

if ($env:OS -ne 'Windows_NT') {
    throw '이 실행기는 Windows 개발 PC에서만 사용할 수 있습니다.'
}
if ($TargetHost -notmatch '^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$') {
    throw 'TargetHost는 credential이나 공백이 없는 IPv4 또는 DNS 이름이어야 합니다.'
}
if ($Port -lt 1 -or $Port -gt 65535) {
    throw 'SSH port 범위가 올바르지 않습니다.'
}
if ($RemoteWorkRoot -notmatch '^[A-Za-z]:\\[A-Za-z0-9_.\\-]+$' -or
    $RemoteWorkRoot -match '[\r\n'']') {
    throw 'RemoteWorkRoot는 단순한 Windows 절대 경로여야 합니다.'
}
if ($ArduinoCli -notmatch '^[A-Za-z]:\\[^\r\n'']+\.exe$') {
    throw 'ArduinoCli는 quote와 줄바꿈이 없는 Windows 실행 파일 경로여야 합니다.'
}
if ($SerialPort -ne 'auto' -and $SerialPort -notmatch '^COM[1-9][0-9]{0,2}$') {
    throw 'SerialPort는 auto 또는 COM1..COM999여야 합니다.'
}
foreach ($timeout in @(
    $ArduinoGateTimeoutSeconds,
    $ZephyrGateTimeoutSeconds,
    $HilGateTimeoutSeconds
)) {
    if ($timeout -lt 60 -or $timeout -gt 86400) {
        throw '개별 gate timeout은 60..86400초여야 합니다.'
    }
}
$minimumSshTimeout = $ArduinoGateTimeoutSeconds + $ZephyrGateTimeoutSeconds + $HilGateTimeoutSeconds + 600
if ($SshTimeoutSeconds -lt $minimumSshTimeout -or $SshTimeoutSeconds -gt 259200) {
    throw "SSH timeout은 개별 gate 합계보다 600초 이상 길어야 합니다: 최소 $minimumSshTimeout"
}

$releaseRootPath = (Resolve-Path -LiteralPath $ReleaseRoot).Path
$planPath = Join-Path $releaseRootPath 'm11-rc-plan.json'
Assert-RegularFile -Path $planPath -Label 'M11 RC plan'
Assert-RegularFile -Path $IdentityFile -Label 'SSH private key'
Assert-RegularFile -Path $KnownHostsFile -Label 'SSH known_hosts'
if ($IdentityFile.EndsWith('.pub', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'IdentityFile에는 공개키가 아니라 private key 경로가 필요합니다.'
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repositoryRoot = (Resolve-Path (Join-Path $scriptRoot '..\..')).Path
$releaseTool = Join-Path $scriptRoot 'nu54_release.py'
Assert-RegularFile -Path $releaseTool -Label 'M11 release tool'
$pythonCommand = (Get-Command $LocalPython -ErrorAction Stop).Source
$sshCommand = (Get-Command ssh.exe -ErrorAction Stop).Source
$scpCommand = (Get-Command scp.exe -ErrorAction Stop).Source
$sshKeygenCommand = (Get-Command ssh-keygen.exe -ErrorAction Stop).Source

$script:CurrentRunId = $RunId
if (-not $script:CurrentRunId) {
    $script:CurrentRunId = 'm11-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
}
if (-not $EvidenceRoot) {
    $EvidenceRoot = Join-Path $repositoryRoot 'build\m11\remote'
}
$localRunRoot = Join-Path $EvidenceRoot $script:CurrentRunId
if (Test-Path -LiteralPath $localRunRoot) {
    throw "같은 M11 run output이 이미 존재합니다: $localRunRoot"
}
$script:LocalTemporaryRoot = Join-Path $localRunRoot 'tmp'
$script:LocalLogPath = Join-Path $localRunRoot 'orchestrator.log'
$script:OrchestratorResultPath = Join-Path $localRunRoot 'orchestrator.json'
New-Item -ItemType Directory -Path $script:LocalTemporaryRoot -Force | Out-Null
Write-Utf8WithoutBom -Path $script:LocalLogPath -Text ''

$script:SshTarget = "$RemoteUser@$TargetHost"
$script:SensitiveLogValues = @(
    $TargetHost,
    $script:SshTarget,
    $IdentityFile,
    $KnownHostsFile
)
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
$knownHostLookup = if ($Port -eq 22) { $TargetHost } else { "[$TargetHost]:$Port" }
Invoke-LocalNative `
    -FilePath $sshKeygenCommand `
    -Arguments @('-F', $knownHostLookup, '-f', $KnownHostsFile) `
    -Label 'known-host-pin-preflight' `
    -TimeoutSeconds 30 | Out-Null

Invoke-LocalNative `
    -FilePath $pythonCommand `
    -Arguments @($releaseTool, 'validate-plan', '--plan', $planPath) `
    -Label 'local-validate-plan' `
    -TimeoutSeconds 600 | Out-Null
$bundle = Get-ReleaseBundle -PlanPath $planPath -Root $releaseRootPath
$script:Plan = $bundle.plan
$script:PlanSha256 = $bundle.plan_sha256

$remoteRunWindows = "$RemoteWorkRoot\runs\$($script:CurrentRunId)"
$remoteReleaseWindows = "$remoteRunWindows\release"
$remoteRepositoryWindows = "$remoteRunWindows\repository"
$remoteRunScp = $remoteRunWindows -replace '\\', '/'
$remoteReleaseScp = $remoteReleaseWindows -replace '\\', '/'

$remoteInitializeTemplate = @'
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$runRoot = '__RUN_ROOT__'
$releaseRoot = '__RELEASE_ROOT__'
$expectedToolchain = '__TOOLCHAIN_ID__'
$expectedNcs = '__NCS_VERSION__'
$arduinoCli = '__ARDUINO_CLI__'
$expectedCliSha256 = '__ARDUINO_CLI_SHA256__'
if (Test-Path -LiteralPath $runRoot) {
    throw 'M11 remote run directory already exists.'
}
New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null
$readyPath = Join-Path $env:LOCALAPPDATA 'NUCODE\NU54DK_Arduino_Core\prerequisites\ready.json'
if (-not (Test-Path -LiteralPath $readyPath -PathType Leaf)) {
    throw 'M10 prerequisite ready.json is missing.'
}
$ready = Get-Content -LiteralPath $readyPath -Raw -Encoding UTF8 | ConvertFrom-Json
$expectedNcsRoot = Join-Path $env:USERPROFILE 'ncs'
$expectedToolchainRoot = Join-Path (Join-Path $expectedNcsRoot 'toolchains') $expectedToolchain
if ($ready.schema_version -ne 1 -or
    $ready.status -ne 'ready' -or
    $ready.ncs_version -ne $expectedNcs -or
    $ready.toolchain_bundle_id -ne $expectedToolchain -or
    [IO.Path]::GetFullPath([string]$ready.ncs_root).TrimEnd('\') -ne [IO.Path]::GetFullPath($expectedNcsRoot).TrimEnd('\') -or
    [IO.Path]::GetFullPath([string]$ready.toolchain_root).TrimEnd('\') -ne [IO.Path]::GetFullPath($expectedToolchainRoot).TrimEnd('\')) {
    throw 'M10 prerequisite ready identity is not the pinned NCS/toolchain.'
}
$python = Join-Path $expectedToolchainRoot 'opt\bin\python.exe'
$git = Join-Path $expectedToolchainRoot 'bin\git.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf) -or
    -not (Test-Path -LiteralPath $git -PathType Leaf) -or
    -not (Test-Path -LiteralPath $arduinoCli -PathType Leaf)) {
    throw 'Pinned Toolchain Python/Git or Arduino CLI is missing.'
}
$actualCliSha256 = (Get-FileHash -LiteralPath $arduinoCli -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualCliSha256 -ne $expectedCliSha256) {
    throw 'Arduino CLI executable SHA-256 is not pinned 1.5.2-rc.1.'
}
'NU54_M11_REMOTE_PREFLIGHT=ready'
'@
$remoteInitialize = $remoteInitializeTemplate.Replace('__RUN_ROOT__', $remoteRunWindows).
    Replace('__RELEASE_ROOT__', $remoteReleaseWindows).
    Replace('__TOOLCHAIN_ID__', $script:ExpectedToolchainBundleId).
    Replace('__NCS_VERSION__', $script:ExpectedNcsVersion).
    Replace('__ARDUINO_CLI__', $ArduinoCli).
    Replace('__ARDUINO_CLI_SHA256__', $script:ExpectedArduinoCliSha256)
$encodedInitialize = Convert-ToEncodedPowerShellCommand -Command $remoteInitialize
Invoke-LocalNative `
    -FilePath $sshCommand `
    -Arguments ($sshOptions + @(
        $script:SshTarget,
        'powershell.exe',
        '-NoProfile',
        '-NonInteractive',
        '-ExecutionPolicy',
        'Bypass',
        '-EncodedCommand',
        $encodedInitialize
    )) `
    -Label 'remote-m11-preflight' `
    -TimeoutSeconds 180 | Out-Null

foreach ($sourcePath in @($bundle.files)) {
    $fileName = [IO.Path]::GetFileName([string]$sourcePath)
    Invoke-LocalNative `
        -FilePath $scpCommand `
        -Arguments ($scpOptions + @(
            [string]$sourcePath,
            ("{0}:{1}/{2}" -f $script:SshTarget, $remoteReleaseScp, $fileName)
        )) `
        -Label ("upload-{0}" -f $fileName) `
        -TimeoutSeconds 300 | Out-Null
}

$remoteGateTemplate = @'
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repositoryUrl = '__REPOSITORY_URL__'
$repositoryRoot = '__REPOSITORY_ROOT__'
$releaseRoot = '__RELEASE_ROOT__'
$coreRevision = '__CORE_REVISION__'
$toolchainRoot = Join-Path (Join-Path (Join-Path $env:USERPROFILE 'ncs') 'toolchains') '__TOOLCHAIN_ID__'
$python = Join-Path $toolchainRoot 'opt\bin\python.exe'
$git = Join-Path $toolchainRoot 'bin\git.exe'
$arduinoCli = '__ARDUINO_CLI__'
$plan = Join-Path $releaseRoot 'm11-rc-plan.json'
$emptyGitConfig = Join-Path $runRoot 'gitconfig.empty'
[IO.File]::WriteAllBytes($emptyGitConfig, [byte[]]@())
$env:GIT_CONFIG_NOSYSTEM = '1'
$env:GIT_CONFIG_GLOBAL = $emptyGitConfig
$env:GIT_TERMINAL_PROMPT = '0'
$env:PATH = (Split-Path -Parent $git) + [IO.Path]::PathSeparator + $env:PATH
& $git -c credential.helper= -c core.longpaths=true clone --no-checkout $repositoryUrl $repositoryRoot
if ($LASTEXITCODE -ne 0) { throw 'Public repository clone failed.' }
& $git -C $repositoryRoot checkout --detach $coreRevision
if ($LASTEXITCODE -ne 0) { throw 'Exact RC commit checkout failed.' }
& $git -C $repositoryRoot -c core.longpaths=true submodule update --init --recursive
if ($LASTEXITCODE -ne 0) { throw 'Exact board submodule checkout failed.' }
$head = (& $git -C $repositoryRoot rev-parse HEAD).Trim()
$status = (& $git -C $repositoryRoot status --porcelain=v1 --untracked-files=all --ignore-submodules=none) -join "`n"
if ($LASTEXITCODE -ne 0 -or $head -ne $coreRevision -or $status) {
    throw 'Remote repository is not the exact clean RC commit.'
}
$releaseTool = Join-Path $repositoryRoot 'tools\release\nu54_release.py'
& $python $releaseTool validate-plan --plan $plan
if ($LASTEXITCODE -ne 0) { throw 'Transferred RC plan or artifact byte validation failed.' }
$gates = @(
    [pscustomobject]@{
        id = 'arduino_cli_fixed_package'
        timeout = __ARDUINO_TIMEOUT__
        cli = $true
        serial = $false
    },
    [pscustomobject]@{
        id = 'zephyr_regression'
        timeout = __ZEPHYR_TIMEOUT__
        cli = $false
        serial = $false
    },
    [pscustomobject]@{
        id = 'hil_rc_pyocd'
        timeout = __HIL_TIMEOUT__
        cli = $true
        serial = $true
    }
)
foreach ($gate in $gates) {
    $output = Join-Path $releaseRoot ($gate.id + '.evidence.json')
    $arguments = @(
        $releaseTool,
        'run-gate',
        '--repo-root',
        $repositoryRoot,
        '--plan',
        $plan,
        '--gate',
        $gate.id,
        '--output',
        $output,
        '--timeout-seconds',
        [string]$gate.timeout
    )
    if ($gate.cli) {
        $arguments += @('--arduino-cli', $arduinoCli)
    }
    if ($gate.serial) {
        $arguments += @('--serial-port', '__SERIAL_PORT__')
    }
    & $python @arguments
    if ($LASTEXITCODE -ne 0) {
        throw ('Fixed M11 gate failed: ' + $gate.id)
    }
}
'NU54_M11_REMOTE_GATES=passed'
'@
$remoteGateCommand = $remoteGateTemplate.Replace('__REPOSITORY_URL__', $script:RepositoryUrl).
    Replace('__REPOSITORY_ROOT__', $remoteRepositoryWindows).
    Replace('__RELEASE_ROOT__', $remoteReleaseWindows).
    Replace('__CORE_REVISION__', [string]$script:Plan.core_revision).
    Replace('__TOOLCHAIN_ID__', $script:ExpectedToolchainBundleId).
    Replace('__ARDUINO_CLI__', $ArduinoCli).
    Replace('__ARDUINO_TIMEOUT__', [string]$ArduinoGateTimeoutSeconds).
    Replace('__ZEPHYR_TIMEOUT__', [string]$ZephyrGateTimeoutSeconds).
    Replace('__HIL_TIMEOUT__', [string]$HilGateTimeoutSeconds).
    Replace('__SERIAL_PORT__', $SerialPort)
$encodedGates = Convert-ToEncodedPowerShellCommand -Command $remoteGateCommand
$remoteFailure = $null
$downloadFailures = New-Object Collections.Generic.List[string]
try {
    Invoke-LocalNative `
        -FilePath $sshCommand `
        -Arguments ($sshOptions + @(
            $script:SshTarget,
            'powershell.exe',
            '-NoProfile',
            '-NonInteractive',
            '-ExecutionPolicy',
            'Bypass',
            '-EncodedCommand',
            $encodedGates
        )) `
        -Label 'remote-m11-fixed-gates' `
        -TimeoutSeconds $SshTimeoutSeconds | Out-Null
} catch {
    $remoteFailure = Protect-LogText -Text $_.Exception.Message
} finally {
    foreach ($fileName in $script:ExpectedResultFiles) {
        $destination = Join-Path $localRunRoot $fileName
        try {
            Invoke-LocalNative `
                -FilePath $scpCommand `
                -Arguments ($scpOptions + @(
                    ("{0}:{1}/{2}" -f $script:SshTarget, $remoteReleaseScp, $fileName),
                    $destination
                )) `
                -Label ("download-{0}" -f $fileName) `
                -TimeoutSeconds 300 | Out-Null
        } catch {
            $downloadFailures.Add($fileName)
        }
    }
}

if ($remoteFailure -or $downloadFailures.Count -ne 0) {
    $failureParts = New-Object Collections.Generic.List[string]
    if ($remoteFailure) {
        $failureParts.Add($remoteFailure)
    }
    if ($downloadFailures.Count -ne 0) {
        $failureParts.Add('회수하지 못한 결과: ' + (($downloadFailures | Sort-Object) -join ', '))
    }
    $failure = Protect-LogText -Text ($failureParts -join '; ')
    Write-OrchestratorResult -Status failed -Failure $failure
    throw $failure
}

$evidencePaths = @(
    Join-Path $localRunRoot 'arduino_cli_fixed_package.evidence.json'
    Join-Path $localRunRoot 'zephyr_regression.evidence.json'
    Join-Path $localRunRoot 'hil_rc_pyocd.evidence.json'
)
$validator = @'
import importlib.util
import pathlib
import sys
module_path = pathlib.Path(sys.argv[1]).resolve()
spec = importlib.util.spec_from_file_location("nu54_m11_remote_validation", module_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
plan_path = pathlib.Path(sys.argv[2]).resolve()
plan = module.validate_plan(plan_path)
for evidence in sys.argv[3:]:
    module.validate_gate_evidence(plan_path, plan, pathlib.Path(evidence))
print("NU54_M11_REMOTE_EVIDENCE=valid")
'@
Invoke-LocalNative `
    -FilePath $pythonCommand `
    -Arguments (@('-c', $validator, $releaseTool, $planPath) + $evidencePaths) `
    -Label 'local-validate-remote-evidence' `
    -TimeoutSeconds 600 | Out-Null

$gateRecords = New-Object Collections.Generic.List[object]
foreach ($gateId in $script:RemoteGateIds) {
    $evidencePath = Join-Path $localRunRoot ($gateId + '.evidence.json')
    $logPath = Join-Path $localRunRoot ($gateId + '.evidence.log')
    $record = [ordered]@{
        gate_id = $gateId
        status = 'passed'
        evidence_file = [IO.Path]::GetFileName($evidencePath)
        evidence_sha256 = Get-FileSha256 -Path $evidencePath
        log_file = [IO.Path]::GetFileName($logPath)
        log_sha256 = Get-FileSha256 -Path $logPath
    }
    if ($gateId -eq 'hil_rc_pyocd') {
        $resultPath = Join-Path $localRunRoot 'hil_rc_pyocd.evidence.result.json'
        $record['result_file'] = [IO.Path]::GetFileName($resultPath)
        $record['result_sha256'] = Get-FileSha256 -Path $resultPath
    }
    $gateRecords.Add([pscustomobject]$record)
}
Write-OrchestratorResult -Status passed -GateRecords @($gateRecords)
Remove-Item -LiteralPath $script:LocalTemporaryRoot -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "NU54_M11_REMOTE_RUN=passed:$localRunRoot"
