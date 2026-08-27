[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$ConfigPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Utf8NoBom {
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

function Write-AtomicUtf8NoBom {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Text
    )

    $directory = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $directory -PathType Container)) {
        throw "Atomic write directory is missing: $directory"
    }
    $temporaryPath = Join-Path $directory ('.' + [IO.Path]::GetFileName($Path) + '.' + [Guid]::NewGuid().ToString('N') + '.tmp')
    $backupPath = Join-Path $directory ('.' + [IO.Path]::GetFileName($Path) + '.' + [Guid]::NewGuid().ToString('N') + '.bak')
    $encoding = New-Object System.Text.UTF8Encoding($false)
    $bytes = $encoding.GetBytes($Text)
    try {
        $stream = [IO.FileStream]::new(
            $temporaryPath,
            [IO.FileMode]::CreateNew,
            [IO.FileAccess]::Write,
            [IO.FileShare]::None,
            4096,
            [IO.FileOptions]::WriteThrough
        )
        try {
            $stream.Write($bytes, 0, $bytes.Length)
            $stream.Flush($true)
        } finally {
            $stream.Dispose()
        }
        if (Test-Path -LiteralPath $Path -PathType Leaf) {
            [IO.File]::Replace($temporaryPath, $Path, $backupPath, $true)
            Remove-Item -LiteralPath $backupPath -Force -ErrorAction SilentlyContinue
        } else {
            [IO.File]::Move($temporaryPath, $Path)
        }
    } finally {
        Remove-Item -LiteralPath $temporaryPath -Force -ErrorAction SilentlyContinue
    }
}

function Enter-RunMutex {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RunRoot
    )

    $algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        $digest = [BitConverter]::ToString(
            $algorithm.ComputeHash([Text.Encoding]::UTF8.GetBytes($RunRoot.ToLowerInvariant()))
        ).Replace('-', '').ToLowerInvariant()
    } finally {
        $algorithm.Dispose()
    }
    $name = 'Global\NUCODE_NU54DK_M10_' + $digest.Substring(0, 32)
    $mutex = [Threading.Mutex]::new($false, $name)
    $acquired = $false
    $abandoned = $false
    try {
        try {
            $acquired = $mutex.WaitOne(0)
        } catch [Threading.AbandonedMutexException] {
            $acquired = $true
            $abandoned = $true
        }
        if (-not $acquired) {
            throw 'Another process already owns this M10 run identity.'
        }
        return [pscustomobject][ordered]@{
            mutex = $mutex
            name = $name
            abandoned_recovered = $abandoned
            owned = $true
        }
    } catch {
        if (-not $acquired) {
            $mutex.Dispose()
        }
        throw
    }
}

function Exit-RunMutex {
    param(
        [object]$Handle
    )

    if ($null -eq $Handle) {
        return
    }
    if ($Handle.owned) {
        $Handle.mutex.ReleaseMutex()
        $Handle.owned = $false
    }
    $Handle.mutex.Dispose()
}

function Protect-Text {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Text
    )

    $protected = $Text
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
        '(?i)(token|password|secret|authorization)\s*[:=]\s*[^\s,;]+',
        '$1=<redacted>'
    )
    return $protected
}

function Get-ConfigValue {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Config,
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [object]$DefaultValue = $null
    )

    $property = $Config.PSObject.Properties[$Name]
    if ($null -eq $property -or $null -eq $property.Value) {
        return $DefaultValue
    }
    return $property.Value
}

function Convert-ToCommandArgument {
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

function Add-RunLog {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text
    )

    $safe = Protect-Text -Text $Text
    [System.IO.File]::AppendAllText(
        $script:RunLogPath,
        $safe + [Environment]::NewLine,
        (New-Object System.Text.UTF8Encoding($false))
    )
    Write-Host $safe
}

function Get-PyOcdProbeCount {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Text
    )

    $withoutAnsi = [regex]::Replace(
        $Text,
        ([string][char]27 + '\[[0-?]*[ -/]*[@-~]'),
        ''
    )
    $lines = @(
        $withoutAnsi -split "`r?`n" |
            ForEach-Object { $_.TrimEnd() } |
            Where-Object { $_.Trim().Length -gt 0 }
    )
    if ($lines.Count -eq 0) {
        return 0
    }
    if ($lines.Count -eq 1 -and
        $lines[0].Trim() -eq 'No available debug probes are connected') {
        return 0
    }
    if (@($lines | Where-Object {
        $_ -match '(?i)no available debug probes'
    }).Count -gt 0) {
        throw 'Ambiguous pyOCD output mixed a no-probe message with other text.'
    }

    $headerCount = @($lines | Where-Object {
        $_ -match '^\|\s*#\s+Probe/Board\s+Unique ID\s+Target\s*\|$'
    }).Count
    if ($headerCount -ne 1) {
        throw 'Unrecognized pyOCD probe table header.'
    }

    $indexes = New-Object System.Collections.Generic.List[int]
    $probeRowSeen = $false
    foreach ($line in $lines) {
        if ($line -match '^\+-+\+$' -or
            $line -match '^\|\s*#\s+Probe/Board\s+Unique ID\s+Target\s*\|$') {
            continue
        }
        if ($line -match '^\| (\d+)\s{2,}\S.*\|$') {
            $indexes.Add([int]$Matches[1])
            $probeRowSeen = $true
            continue
        }
        if ($probeRowSeen -and $line -match '^\|\s{2,}.*\|$') {
            continue
        }
        throw 'Unrecognized or ambiguous pyOCD probe table row.'
    }
    if ($indexes.Count -eq 0) {
        throw 'pyOCD emitted a table without a recognizable probe row.'
    }
    for ($index = 0; $index -lt $indexes.Count; $index++) {
        if ($indexes[$index] -ne $index) {
            throw 'pyOCD probe indexes are not unique and contiguous.'
        }
    }
    return $indexes.Count
}

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [string[]]$Arguments = @(),
        [Parameter(Mandatory = $true)]
        [string]$Label,
        [int]$TimeoutSeconds = 1800,
        [string]$WorkingDirectory = $script:RunRoot,
        [int[]]$AllowedExitCodes = @(0)
    )

    if ($TimeoutSeconds -lt 1) {
        throw "Invalid timeout for $Label."
    }
    if (-not (Test-Path -LiteralPath $FilePath -PathType Leaf)) {
        throw "Executable not found for ${Label}: $FilePath"
    }
    if (-not (Test-Path -LiteralPath $WorkingDirectory -PathType Container)) {
        throw "Working directory not found for ${Label}: $WorkingDirectory"
    }

    $commandLine = (@($Arguments | ForEach-Object {
        Convert-ToCommandArgument -Value ([string]$_)
    }) -join ' ')
    $commandId = [Guid]::NewGuid().ToString('N')
    $stdoutPath = Join-Path $script:TemporaryRoot ($commandId + '.stdout.txt')
    $stderrPath = Join-Path $script:TemporaryRoot ($commandId + '.stderr.txt')
    $started = [DateTime]::UtcNow
    Add-RunLog -Text ("COMMAND START [{0}] {1}" -f $Label, $FilePath)

    $process = Start-Process `
        -FilePath $FilePath `
        -ArgumentList $commandLine `
        -WorkingDirectory $WorkingDirectory `
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

    $duration = [Math]::Round(([DateTime]::UtcNow - $started).TotalSeconds, 3)
    if ($stdout) {
        Add-RunLog -Text $stdout.TrimEnd()
    }
    if ($stderr) {
        Add-RunLog -Text $stderr.TrimEnd()
    }

    if (-not $completed) {
        throw "Command timed out after $TimeoutSeconds seconds: $Label"
    }
    $exitCode = $process.ExitCode
    if ($AllowedExitCodes -notcontains $exitCode) {
        throw "Command failed with exit code ${exitCode}: $Label"
    }
    Add-RunLog -Text ("COMMAND PASS [{0}] duration={1}s" -f $Label, $duration)

    return [pscustomobject][ordered]@{
        exit_code = $exitCode
        duration_seconds = $duration
        stdout = $stdout
        stderr = $stderr
    }
}

function Save-State {
    $stateObject = [ordered]@{
        schema_version = 2
        run_id = $script:RunId
        fingerprint = $script:RunFingerprint
        status = $script:RunStatus
        started_at_utc = $script:StartedAtUtc
        updated_at_utc = [DateTime]::UtcNow.ToString('o')
        initial_environment = $script:InitialEnvironment
        steps = $script:StepState
    }
    Write-AtomicUtf8NoBom `
        -Path $script:StatePath `
        -Text (($stateObject | ConvertTo-Json -Depth 20) + [Environment]::NewLine)
}

function Save-Evidence {
    param(
        [string]$Failure = ''
    )

    $steps = @()
    foreach ($name in $script:StepOrder) {
        if ($script:StepState.ContainsKey($name)) {
            $steps += $script:StepState[$name]
        }
    }
    $evidence = [ordered]@{
        schema_version = 2
        milestone = 'M10'
        run_id = $script:RunId
        status = $script:RunStatus
        started_at_utc = $script:StartedAtUtc
        updated_at_utc = [DateTime]::UtcNow.ToString('o')
        completed_at_utc = if ($script:RunStatus -eq 'passed') {
            [DateTime]::UtcNow.ToString('o')
        } else {
            $null
        }
        configuration = [ordered]@{
            index_url = $script:IndexUrl
            fqbn = $script:Fqbn
            initial_version = $script:InitialVersion
            latest_version = $script:LatestVersion
            ncs_version = $script:NcsVersion
            toolchain_bundle_id = $script:ToolchainBundleId
            require_probe = $script:RequireProbe
            index_sha256 = $script:ExpectedIndexSha256
            archives = $script:ArchiveIdentities
            target_runner_sha256 = $script:ActualRunnerSha256
            arduino_cli = [ordered]@{
                expected_version = $script:ExpectedArduinoCliVersion
                expected_commit = $script:ExpectedArduinoCliCommit
                executable_sha256 = $script:ActualArduinoCliSha256
            }
        }
        initial_environment = $script:InitialEnvironment
        isolation = [ordered]@{
            data = $script:DataRoot
            downloads = $script:DownloadsRoot
            sketchbook = $script:SketchbookRoot
            build = $script:BuildRoot
        }
        steps = $steps
        failure = if ($Failure) { Protect-Text -Text $Failure } else { $null }
        redaction = [ordered]@{
            device_identifiers = $true
            credentials = $true
        }
    }
    Write-AtomicUtf8NoBom `
        -Path $script:EvidencePath `
        -Text (($evidence | ConvertTo-Json -Depth 20) + [Environment]::NewLine)
}

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [scriptblock]$Action
    )

    if ($script:StepState.ContainsKey($Name)) {
        $existing = $script:StepState[$Name]
        if ($existing.status -eq 'passed') {
            Add-RunLog -Text "STEP RESUME PASS [$Name]"
            return $existing.result
        }
    }

    $started = [DateTime]::UtcNow
    Add-RunLog -Text "STEP START [$Name]"
    try {
        $result = & $Action
        $entry = [pscustomobject][ordered]@{
            name = $Name
            status = 'passed'
            started_at_utc = $started.ToString('o')
            completed_at_utc = [DateTime]::UtcNow.ToString('o')
            duration_seconds = [Math]::Round(([DateTime]::UtcNow - $started).TotalSeconds, 3)
            result = $result
        }
        $script:StepState[$Name] = $entry
        Save-State
        Save-Evidence
        Add-RunLog -Text "STEP PASS [$Name]"
        return $result
    } catch {
        $failureResult = $null
        if ($_.Exception.Data.Contains('nu54_result')) {
            $failureResult = $_.Exception.Data['nu54_result']
        }
        $entry = [pscustomobject][ordered]@{
            name = $Name
            status = 'failed'
            started_at_utc = $started.ToString('o')
            completed_at_utc = [DateTime]::UtcNow.ToString('o')
            duration_seconds = [Math]::Round(([DateTime]::UtcNow - $started).TotalSeconds, 3)
            result = $failureResult
            error = Protect-Text -Text $_.Exception.Message
        }
        $script:StepState[$Name] = $entry
        $script:RunStatus = 'failed'
        Save-State
        Save-Evidence -Failure $_.Exception.Message
        Add-RunLog -Text "STEP FAIL [$Name] $($_.Exception.Message)"
        throw
    }
}

function Get-PlatformRoot {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Version
    )

    return Join-Path $script:DataRoot ("packages\nucode\hardware\zephyr\{0}" -f $Version)
}

function Get-ExpectedArchiveIdentity {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Version
    )

    $property = $script:ArchiveIdentities.PSObject.Properties[$Version]
    if ($null -eq $property) {
        throw "Expected archive identity is missing for version $Version."
    }
    return $property.Value
}

function Assert-CachedIndexIdentity {
    $matches = @(Get-ChildItem `
        -LiteralPath $script:DataRoot `
        -Filter $script:IndexFileName `
        -File `
        -Recurse `
        -ErrorAction SilentlyContinue)
    if ($matches.Count -ne 1) {
        throw "Expected exactly one cached package index, found $($matches.Count)."
    }
    $digest = (Get-FileHash -LiteralPath $matches[0].FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($digest -ne $script:ExpectedIndexSha256) {
        throw 'Cached package index SHA-256 does not match the orchestrator snapshot.'
    }
    return [pscustomobject][ordered]@{
        sha256 = $digest
        file_name = $script:IndexFileName
    }
}

function Get-InstalledReleaseIdentity {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Version
    )

    $platformRoot = Get-PlatformRoot -Version $Version
    $manifestPath = Join-Path $platformRoot 'release-manifest.json'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw "Installed release manifest is missing: $manifestPath"
    }
    try {
        $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        throw "Installed release manifest is not valid JSON for version $Version."
    }
    $expectedArchive = Get-ExpectedArchiveIdentity -Version $Version
    if ($manifest.schema_version -ne 1 -or $manifest.version -ne $Version) {
        throw "Installed release manifest identity is invalid for version $Version."
    }
    if ([string]$manifest.core_revision -notmatch '^[0-9a-f]{40}$' -or
        [string]$manifest.board_revision -notmatch '^[0-9a-f]{40}$') {
        throw "Installed release Git revision is invalid for version $Version."
    }
    if ([string]$manifest.core_revision -ne [string]$expectedArchive.core_revision) {
        throw "Installed release core revision does not match the prevalidated archive for version $Version."
    }
    if ([string]$manifest.archive_file_name -ne [string]$expectedArchive.file_name) {
        throw "Installed release archive name does not match the index for version $Version."
    }
    if ([string]$manifest.toolchain_bundle_id -ne $script:ToolchainBundleId) {
        throw "Installed release toolchain identity is invalid for version $Version."
    }
    $pinsPath = Join-Path $platformRoot 'tools\nu54-prerequisites\pins.json'
    if (-not (Test-Path -LiteralPath $pinsPath -PathType Leaf)) {
        throw "Installed prerequisite pins are missing for version $Version."
    }
    $pinsSha256 = (Get-FileHash -LiteralPath $pinsPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ([string]$manifest.prerequisites_pins_sha256 -ne $pinsSha256) {
        throw "Installed release pins checksum is invalid for version $Version."
    }
    $releaseManifestSha256 = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($releaseManifestSha256 -ne [string]$expectedArchive.release_manifest_sha256) {
        throw "Installed release manifest bytes do not match the prevalidated archive for version $Version."
    }
    return [pscustomobject][ordered]@{
        version = $Version
        core_revision = [string]$manifest.core_revision
        board_revision = [string]$manifest.board_revision
        release_manifest_sha256 = $releaseManifestSha256
        archive_file_name = [string]$expectedArchive.file_name
        archive_sha256 = [string]$expectedArchive.sha256
        archive_size = [string]$expectedArchive.size
        index_sha256 = $script:ExpectedIndexSha256
        prerequisites_pins_sha256 = $pinsSha256
        ncs_revision = [string]$manifest.ncs_revision
        zephyr_revision = [string]$manifest.zephyr_revision
        toolchain_bundle_id = [string]$manifest.toolchain_bundle_id
    }
}

function Invoke-Arduino {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Label,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [int]$TimeoutSeconds = 1800
    )

    $allArguments = @('--config-file', $script:ArduinoConfigPath) + $Arguments
    return Invoke-NativeCommand `
        -FilePath $script:ArduinoCli `
        -Arguments $allArguments `
        -Label $Label `
        -TimeoutSeconds $TimeoutSeconds
}

function Invoke-NordicVerification {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Version
    )

    $platformRoot = Get-PlatformRoot -Version $Version
    $verifyScript = Join-Path $platformRoot 'tools\nu54-prerequisites\verify-nordic.ps1'
    if (-not (Test-Path -LiteralPath $verifyScript -PathType Leaf)) {
        throw "Nordic verification script is missing: $verifyScript"
    }
    $verification = Invoke-NativeCommand `
        -FilePath $script:PowerShellExe `
        -Arguments @(
            '-NoProfile',
            '-NonInteractive',
            '-ExecutionPolicy',
            'Bypass',
            '-File',
            $verifyScript,
            '-PlatformRoot',
            $platformRoot,
            '-NcsRoot',
            $script:NcsBaseRoot,
            '-Json'
        ) `
        -Label ("verify-nordic-{0}" -f $Version) `
        -TimeoutSeconds $script:VerifyTimeoutSeconds

    $jsonText = $verification.stdout.Trim()
    try {
        $verified = $jsonText | ConvertFrom-Json
    } catch {
        throw "Nordic verification did not return valid JSON for version $Version."
    }
    if ($verified.status -ne 'ready') {
        throw "Nordic verification status is not ready for version $Version."
    }
    if ($verified.toolchain_bundle_id -and
        $verified.toolchain_bundle_id -ne $script:ToolchainBundleId) {
        throw "Unexpected toolchain bundle id: $($verified.toolchain_bundle_id)"
    }

    return [pscustomobject][ordered]@{
        status = 'ready'
        platform_version = $Version
        ncs_version = $script:NcsVersion
        toolchain_bundle_id = $script:ToolchainBundleId
        pins_sha256 = $verified.pins_sha256
    }
}

function Assert-CoreVersion {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Version
    )

    $listed = Invoke-Arduino `
        -Label ("core-list-{0}" -f $Version) `
        -Arguments @('core', 'list', '--json') `
        -TimeoutSeconds 120
    if ($listed.stdout -notmatch [regex]::Escape($Version)) {
        throw "Installed core version $Version was not reported by Arduino CLI."
    }
    if ($listed.stdout -notmatch 'nucode:zephyr') {
        throw 'Installed nucode:zephyr core was not reported by Arduino CLI.'
    }
}

function Test-Nu54CoreInstalled {
    $listed = Invoke-Arduino `
        -Label 'core-list-install-state' `
        -Arguments @('core', 'list', '--json') `
        -TimeoutSeconds 120
    try {
        $coreList = $listed.stdout | ConvertFrom-Json
    } catch {
        throw 'Arduino CLI core list did not return valid JSON.'
    }
    if ($null -eq $coreList.PSObject.Properties['platforms']) {
        throw 'Arduino CLI core list JSON is missing the platforms array.'
    }
    $matches = @($coreList.platforms | Where-Object {
        $null -ne $_.PSObject.Properties['id'] -and
        $_.id -eq 'nucode:zephyr'
    })
    if ($matches.Count -gt 1) {
        throw 'Arduino CLI reported duplicate nucode:zephyr installations.'
    }
    return ($matches.Count -eq 1)
}

function Ensure-Nu54CoreAbsent {
    $wasInstalled = Test-Nu54CoreInstalled
    $uninstallInvoked = $false
    if ($wasInstalled) {
        Invoke-Arduino `
            -Label 'core-uninstall' `
            -Arguments @('core', 'uninstall', 'nucode:zephyr') `
            -TimeoutSeconds 600 | Out-Null
        $uninstallInvoked = $true
    } else {
        Add-RunLog -Text 'CORE UNINSTALL RECOVERY: nucode:zephyr is already absent.'
    }
    if (Test-Nu54CoreInstalled) {
        throw 'nucode:zephyr is still installed after the idempotent uninstall step.'
    }
    return [pscustomobject][ordered]@{
        core_was_installed = $wasInstalled
        uninstall_invoked = $uninstallInvoked
        recovered_after_prior_uninstall = (-not $wasInstalled)
    }
}

function Install-CoreVersion {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Version
    )

    Invoke-Arduino `
        -Label ("core-install-{0}" -f $Version) `
        -Arguments @(
            'core',
            'install',
            ("nucode:zephyr@{0}" -f $Version),
            '--run-post-install'
        ) `
        -TimeoutSeconds $script:InstallTimeoutSeconds | Out-Null
    Assert-CoreVersion -Version $Version
    $nordic = Invoke-NordicVerification -Version $Version
    $release = Get-InstalledReleaseIdentity -Version $Version
    if ($release.prerequisites_pins_sha256 -ne $nordic.pins_sha256) {
        throw "Installed release and Nordic verifier pins differ for version $Version."
    }
    return [pscustomobject][ordered]@{
        nordic = $nordic
        release = $release
    }
}

function Invoke-Compile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Label,
        [Parameter(Mandatory = $true)]
        [string]$BuildPath
    )

    New-Item -ItemType Directory -Path $BuildPath -Force | Out-Null
    $compiled = Invoke-Arduino `
        -Label $Label `
        -Arguments @(
            'compile',
            '--fqbn',
            $script:Fqbn,
            '--build-path',
            $BuildPath,
            '--export-binaries',
            $script:SketchRoot
        ) `
        -TimeoutSeconds $script:BuildTimeoutSeconds
    $manifest = Join-Path $BuildPath 'Blink.ino.nu54-build.json'
    $hex = Join-Path $BuildPath 'Blink.ino.hex'
    if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) {
        throw "Build manifest was not produced: $manifest"
    }
    if (-not (Test-Path -LiteralPath $hex -PathType Leaf)) {
        throw "HEX artifact was not produced: $hex"
    }
    return [pscustomobject][ordered]@{
        duration_seconds = $compiled.duration_seconds
        manifest_sha256 = (Get-FileHash -LiteralPath $manifest -Algorithm SHA256).Hash.ToLowerInvariant()
        hex_sha256 = (Get-FileHash -LiteralPath $hex -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}

if ($env:OS -ne 'Windows_NT') {
    throw 'This runner requires Windows.'
}
$resolvedConfigPath = (Resolve-Path -LiteralPath $ConfigPath).Path
$config = Get-Content -LiteralPath $resolvedConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
$script:RunId = [string](Get-ConfigValue -Config $config -Name 'run_id')
if ($script:RunId -notmatch '^[A-Za-z0-9._-]{1,80}$') {
    throw 'Invalid run_id.'
}
$script:IndexUrl = [string](Get-ConfigValue -Config $config -Name 'index_url')
$indexUri = $null
if (-not [Uri]::TryCreate($script:IndexUrl, [UriKind]::Absolute, [ref]$indexUri) -or
    $indexUri.Scheme -ne 'https') {
    throw 'index_url must be an absolute HTTPS URL.'
}
if ($indexUri.Host -ne 'raw.githubusercontent.com' -or
    $indexUri.AbsolutePath -notmatch '^/EIDOSDATA/NU54DK_Arduino_Core/' -or
    $indexUri.UserInfo -or $indexUri.Query -or $indexUri.Fragment) {
    throw 'index_url must be the public EIDOSDATA raw GitHub URL without credentials or query.'
}
$script:IndexFileName = [IO.Path]::GetFileName($indexUri.AbsolutePath)
if ($script:IndexFileName -ne 'package_nucode_nu54dk_preview_index.json') {
    throw 'Unexpected package index filename.'
}
$script:Fqbn = [string](Get-ConfigValue -Config $config -Name 'fqbn' -DefaultValue 'nucode:zephyr:nu54dk')
if ($script:Fqbn -ne 'nucode:zephyr:nu54dk') {
    throw 'Unexpected FQBN.'
}
$script:InitialVersion = [string](Get-ConfigValue -Config $config -Name 'initial_version' -DefaultValue '0.0.90')
$script:LatestVersion = [string](Get-ConfigValue -Config $config -Name 'latest_version' -DefaultValue '0.0.91')
foreach ($version in @($script:InitialVersion, $script:LatestVersion)) {
    if ($version -notmatch '^\d+\.\d+\.\d+$') {
        throw "Invalid core version: $version"
    }
}
if ([version]$script:LatestVersion -le [version]$script:InitialVersion) {
    throw 'latest_version must be newer than initial_version.'
}
$script:NcsVersion = [string](Get-ConfigValue -Config $config -Name 'ncs_version' -DefaultValue 'v3.4.0')
$script:ToolchainBundleId = [string](Get-ConfigValue -Config $config -Name 'toolchain_bundle_id' -DefaultValue 'dcbdc366a1')
if ($script:ToolchainBundleId -notmatch '^[0-9a-f]{10}$') {
    throw 'Invalid toolchain_bundle_id.'
}
$script:RequireProbe = [bool](Get-ConfigValue -Config $config -Name 'require_probe' -DefaultValue $true)
$script:ExpectedArduinoCliVersion = [string](Get-ConfigValue -Config $config -Name 'arduino_cli_version')
$script:ExpectedArduinoCliCommit = [string](Get-ConfigValue -Config $config -Name 'arduino_cli_commit')
$script:ExpectedArduinoCliSha256 = [string](Get-ConfigValue -Config $config -Name 'arduino_cli_sha256')
$script:ExpectedRunnerSha256 = [string](Get-ConfigValue -Config $config -Name 'target_runner_sha256')
$script:ExpectedIndexSha256 = [string](Get-ConfigValue -Config $config -Name 'index_sha256')
$script:ArchiveIdentities = Get-ConfigValue -Config $config -Name 'archives'
if ($script:ExpectedArduinoCliVersion -notmatch '^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$' -or
    $script:ExpectedArduinoCliCommit -notmatch '^[0-9a-f]{9}$' -or
    $script:ExpectedArduinoCliSha256 -notmatch '^[0-9a-f]{64}$') {
    throw 'Invalid expected Arduino CLI identity.'
}
foreach ($digest in @($script:ExpectedRunnerSha256, $script:ExpectedIndexSha256)) {
    if ([string]$digest -notmatch '^[0-9a-f]{64}$') {
        throw 'Invalid expected SHA-256 identity.'
    }
}
if ($null -eq $script:ArchiveIdentities) {
    throw 'Missing archive identities.'
}
foreach ($version in @($script:InitialVersion, $script:LatestVersion)) {
    $archiveProperty = $script:ArchiveIdentities.PSObject.Properties[$version]
    if ($null -eq $archiveProperty -or
        [string]$archiveProperty.Value.sha256 -notmatch '^[0-9a-f]{64}$' -or
        [string]$archiveProperty.Value.size -notmatch '^[1-9][0-9]*$' -or
        [string]$archiveProperty.Value.core_revision -notmatch '^[0-9a-f]{40}$' -or
        [string]$archiveProperty.Value.release_manifest_sha256 -notmatch '^[0-9a-f]{64}$') {
        throw "Invalid archive identity for version $version."
    }
}

$workRoot = [string](Get-ConfigValue -Config $config -Name 'work_root' -DefaultValue (Join-Path $env:USERPROFILE 'NU54CI\M10'))
$expectedWorkRoot = Join-Path $env:USERPROFILE 'NU54CI\M10'
if ([IO.Path]::GetFullPath($workRoot).TrimEnd('\') -ne
    [IO.Path]::GetFullPath($expectedWorkRoot).TrimEnd('\')) {
    throw 'work_root must be the dedicated NU54CI M10 directory in the current user profile.'
}
$script:RunRoot = Join-Path (Join-Path $workRoot 'runs') $script:RunId
$script:LogsRoot = Join-Path $script:RunRoot 'logs'
$script:TemporaryRoot = Join-Path $script:RunRoot 'tmp'
$script:DataRoot = Join-Path $script:RunRoot 'arduino-data'
$script:DownloadsRoot = Join-Path $script:RunRoot 'downloads'
$script:SketchbookRoot = Join-Path $script:RunRoot 'sketchbook'
$script:BuildRoot = Join-Path $script:RunRoot 'build'
$script:SketchRoot = Join-Path $script:SketchbookRoot 'Blink'
$script:StatePath = Join-Path $script:RunRoot 'state.json'
$script:EvidencePath = Join-Path $script:RunRoot 'evidence.json'
$script:RunLogPath = Join-Path $script:LogsRoot 'runner.log'
$script:ArduinoConfigPath = Join-Path $script:RunRoot 'arduino-cli.yaml'
$script:NcsBaseRoot = Join-Path $env:USERPROFILE 'ncs'
$script:ArduinoCli = [string](Get-ConfigValue -Config $config -Name 'arduino_cli' -DefaultValue 'C:\Program Files\Arduino CLI\arduino-cli.exe')
$script:PowerShellExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$script:InstallTimeoutSeconds = [int](Get-ConfigValue -Config $config -Name 'install_timeout_seconds' -DefaultValue 10800)
$script:BuildTimeoutSeconds = [int](Get-ConfigValue -Config $config -Name 'build_timeout_seconds' -DefaultValue 3600)
$script:VerifyTimeoutSeconds = [int](Get-ConfigValue -Config $config -Name 'verify_timeout_seconds' -DefaultValue 600)
$script:ActualRunnerSha256 = (Get-FileHash -LiteralPath $MyInvocation.MyCommand.Path -Algorithm SHA256).Hash.ToLowerInvariant()
$script:ActualArduinoCliSha256 = if (Test-Path -LiteralPath $script:ArduinoCli -PathType Leaf) {
    (Get-FileHash -LiteralPath $script:ArduinoCli -Algorithm SHA256).Hash.ToLowerInvariant()
} else {
    'missing'
}

foreach ($directory in @(
    $script:RunRoot,
    $script:LogsRoot,
    $script:TemporaryRoot,
    $script:DataRoot,
    $script:DownloadsRoot,
    $script:SketchbookRoot,
    $script:BuildRoot,
    $script:SketchRoot
)) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
}
$script:RunMutexHandle = Enter-RunMutex -RunRoot $script:RunRoot

$script:RunFingerprint = [ordered]@{
    index_url = $script:IndexUrl
    fqbn = $script:Fqbn
    initial_version = $script:InitialVersion
    latest_version = $script:LatestVersion
    ncs_version = $script:NcsVersion
    toolchain_bundle_id = $script:ToolchainBundleId
    require_probe = $script:RequireProbe
    index_sha256 = $script:ExpectedIndexSha256
    archives = $script:ArchiveIdentities
    expected_runner_sha256 = $script:ExpectedRunnerSha256
    actual_runner_sha256 = $script:ActualRunnerSha256
    expected_arduino_cli_version = $script:ExpectedArduinoCliVersion
    expected_arduino_cli_commit = $script:ExpectedArduinoCliCommit
    expected_arduino_cli_sha256 = $script:ExpectedArduinoCliSha256
    actual_arduino_cli_sha256 = $script:ActualArduinoCliSha256
}
$script:StepState = @{}
$script:StepOrder = @(
    'preflight',
    'update_index',
    'install_0_0_90',
    'board_details_0_0_90',
    'blink_cold_compile',
    'blink_warm_compile',
    'probe_and_upload',
    'upgrade_0_0_91',
    'downgrade_0_0_90',
    'uninstall_preserves_ncs',
    'reinstall_latest'
)
$script:RunStatus = 'running'
$script:StartedAtUtc = [DateTime]::UtcNow.ToString('o')
$script:InitialEnvironment = [ordered]@{
    ncs_exists = (Test-Path -LiteralPath $script:NcsBaseRoot)
    prerequisite_state_exists = (Test-Path -LiteralPath (Join-Path $env:LOCALAPPDATA 'NUCODE\NU54DK_Arduino_Core\prerequisites'))
    ready_marker_exists = (Test-Path -LiteralPath (Join-Path $env:LOCALAPPDATA 'NUCODE\NU54DK_Arduino_Core\prerequisites\ready.json') -PathType Leaf)
    abandoned_mutex_recovered = $script:RunMutexHandle.abandoned_recovered
}

if (Test-Path -LiteralPath $script:StatePath -PathType Leaf) {
    $loadedState = Get-Content -LiteralPath $script:StatePath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($loadedState.schema_version -ne 2) {
        throw 'Existing run state schema is not supported.'
    }
    $loadedFingerprint = $loadedState.fingerprint | ConvertTo-Json -Compress
    $currentFingerprint = $script:RunFingerprint | ConvertTo-Json -Compress
    if ($loadedFingerprint -ne $currentFingerprint) {
        throw 'Resume fingerprint does not match the existing run.'
    }
    $script:StartedAtUtc = [string]$loadedState.started_at_utc
    $script:InitialEnvironment = $loadedState.initial_environment
    foreach ($property in $loadedState.steps.PSObject.Properties) {
        $script:StepState[$property.Name] = $property.Value
    }
}

$arduinoConfig = @"
board_manager:
  additional_urls:
    - $script:IndexUrl
directories:
  data: $($script:DataRoot.Replace('\', '/'))
  downloads: $($script:DownloadsRoot.Replace('\', '/'))
  user: $($script:SketchbookRoot.Replace('\', '/'))
logging:
  level: info
"@
Write-Utf8NoBom -Path $script:ArduinoConfigPath -Text $arduinoConfig
if ($script:StepState.ContainsKey('update_index') -and
    $script:StepState['update_index'].status -eq 'passed') {
    Assert-CachedIndexIdentity | Out-Null
}
$blinkSketch = @'
void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
}

void loop() {
  digitalWrite(LED_BUILTIN, HIGH);
  delay(250);
  digitalWrite(LED_BUILTIN, LOW);
  delay(250);
}
'@
Write-Utf8NoBom -Path (Join-Path $script:SketchRoot 'Blink.ino') -Text $blinkSketch
Save-State
Save-Evidence

try {
    Invoke-Step -Name 'preflight' -Action {
        if (-not (Test-Path -LiteralPath $script:ArduinoCli -PathType Leaf)) {
            throw "Arduino CLI not found: $script:ArduinoCli"
        }
        if ($script:ActualRunnerSha256 -ne $script:ExpectedRunnerSha256) {
            throw 'Target runner SHA-256 does not match the orchestrator identity.'
        }
        if ($script:ActualArduinoCliSha256 -ne $script:ExpectedArduinoCliSha256) {
            throw 'Arduino CLI executable SHA-256 does not match the pinned identity.'
        }
        if ($script:InitialEnvironment.ncs_exists -or
            $script:InitialEnvironment.prerequisite_state_exists -or
            $script:InitialEnvironment.ready_marker_exists) {
            throw 'Clean Windows baseline already contains NCS or NU54DK prerequisite state.'
        }
        $cliVersion = Invoke-NativeCommand `
            -FilePath $script:ArduinoCli `
            -Arguments @('version', '--json') `
            -Label 'arduino-cli-version' `
            -TimeoutSeconds 120
        try {
            $cliIdentity = $cliVersion.stdout | ConvertFrom-Json
        } catch {
            throw 'Arduino CLI version did not return valid JSON.'
        }
        if ($cliIdentity.Application -ne 'arduino-cli' -or
            $cliIdentity.VersionString -ne $script:ExpectedArduinoCliVersion -or
            $cliIdentity.Commit -ne $script:ExpectedArduinoCliCommit) {
            throw 'Arduino CLI exact version or commit identity does not match.'
        }
        return [pscustomobject][ordered]@{
            arduino_cli_available = $true
            version = [string]$cliIdentity.VersionString
            commit = [string]$cliIdentity.Commit
            executable_sha256 = $script:ActualArduinoCliSha256
            target_runner_sha256 = $script:ActualRunnerSha256
            clean_baseline = $script:InitialEnvironment
        }
    } | Out-Null

    Invoke-Step -Name 'update_index' -Action {
        Invoke-Arduino `
            -Label 'core-update-index' `
            -Arguments @('core', 'update-index') `
            -TimeoutSeconds 600 | Out-Null
        $cachedIndex = Assert-CachedIndexIdentity
        return [pscustomobject][ordered]@{
            index_updated = $true
            index = $cachedIndex
            archives = $script:ArchiveIdentities
        }
    } | Out-Null

    Invoke-Step -Name 'install_0_0_90' -Action {
        return Install-CoreVersion -Version $script:InitialVersion
    } | Out-Null

    Invoke-Step -Name 'board_details_0_0_90' -Action {
        $details = Invoke-Arduino `
            -Label 'board-details-initial' `
            -Arguments @('board', 'details', '--fqbn', $script:Fqbn, '--json') `
            -TimeoutSeconds 120
        if ($details.stdout -notmatch 'nu54dk') {
            throw 'Board details did not report NU54DK.'
        }
        return [pscustomobject][ordered]@{
            fqbn = $script:Fqbn
            details_verified = $true
        }
    } | Out-Null

    $coldBuildPath = Join-Path $script:BuildRoot 'blink'
    Invoke-Step -Name 'blink_cold_compile' -Action {
        return Invoke-Compile -Label 'blink-cold-compile' -BuildPath $coldBuildPath
    } | Out-Null
    Invoke-Step -Name 'blink_warm_compile' -Action {
        return Invoke-Compile -Label 'blink-warm-compile' -BuildPath $coldBuildPath
    } | Out-Null

    Invoke-Step -Name 'probe_and_upload' -Action {
        $platformRoot = Get-PlatformRoot -Version $script:InitialVersion
        $verifyJson = Join-Path $env:LOCALAPPDATA 'NUCODE\NU54DK_Arduino_Core\prerequisites\ready.json'
        if (-not (Test-Path -LiteralPath $verifyJson -PathType Leaf)) {
            throw "Nordic ready state is missing: $verifyJson"
        }
        $ready = Get-Content -LiteralPath $verifyJson -Raw -Encoding UTF8 | ConvertFrom-Json
        $pyocdPath = Join-Path ([string]$ready.toolchain_root) 'opt\bin\Scripts\pyocd.exe'
        $probeList = Invoke-NativeCommand `
            -FilePath $pyocdPath `
            -Arguments @('list', '--probes', '--no-header') `
            -Label 'pyocd-list' `
            -TimeoutSeconds 120
        if ($probeList.stderr.Trim()) {
            throw 'pyOCD probe listing returned unexpected stderr output.'
        }
        $probeCount = Get-PyOcdProbeCount -Text $probeList.stdout
        if ($probeCount -eq 0) {
            if ($script:RequireProbe) {
                $error = [InvalidOperationException]::new(
                    'NU54DK CMSIS-DAP probe is required but no pyOCD probe is attached.'
                )
                $error.Data['nu54_result'] = [pscustomobject][ordered]@{
                    attached = $false
                    probe_count = 0
                    upload = 'blocked-no-probe'
                }
                throw $error
            }
            return [pscustomobject][ordered]@{
                attached = $false
                probe_count = 0
                upload = 'skipped-no-probe'
            }
        }
        if ($probeCount -gt 1) {
            $error = [InvalidOperationException]::new(
                "Multiple pyOCD probes are attached ($probeCount); no explicit probe was selected."
            )
            $error.Data['nu54_result'] = [pscustomobject][ordered]@{
                attached = $true
                probe_count = $probeCount
                upload = 'blocked-ambiguous-probe'
            }
            throw $error
        }
        Invoke-Arduino `
            -Label 'blink-pyocd-upload' `
            -Arguments @(
                'upload',
                '--fqbn',
                $script:Fqbn,
                '--input-dir',
                $coldBuildPath,
                $script:SketchRoot
            ) `
            -TimeoutSeconds 600 | Out-Null
        return [pscustomobject][ordered]@{
            attached = $true
            probe_count = $probeCount
            upload = 'passed'
        }
    } | Out-Null

    Invoke-Step -Name 'upgrade_0_0_91' -Action {
        return Install-CoreVersion -Version $script:LatestVersion
    } | Out-Null
    Invoke-Step -Name 'downgrade_0_0_90' -Action {
        return Install-CoreVersion -Version $script:InitialVersion
    } | Out-Null

    Invoke-Step -Name 'uninstall_preserves_ncs' -Action {
        $readyPath = Join-Path $env:LOCALAPPDATA 'NUCODE\NU54DK_Arduino_Core\prerequisites\ready.json'
        if (-not (Test-Path -LiteralPath $readyPath -PathType Leaf)) {
            throw 'Nordic ready state is missing before uninstall.'
        }
        $readyHashBefore = (Get-FileHash -LiteralPath $readyPath -Algorithm SHA256).Hash
        $ncsVersionPath = Join-Path $script:NcsBaseRoot ($script:NcsVersion + '\zephyr\VERSION')
        if (-not (Test-Path -LiteralPath $ncsVersionPath -PathType Leaf)) {
            throw 'NCS version file is missing before uninstall.'
        }
        $ncsHashBefore = (Get-FileHash -LiteralPath $ncsVersionPath -Algorithm SHA256).Hash
        $coreAbsence = Ensure-Nu54CoreAbsent
        if (-not (Test-Path -LiteralPath $ncsVersionPath -PathType Leaf)) {
            throw 'Shared NCS was removed by core uninstall.'
        }
        $ncsHashAfter = (Get-FileHash -LiteralPath $ncsVersionPath -Algorithm SHA256).Hash
        if ($ncsHashBefore -ne $ncsHashAfter) {
            throw 'Shared NCS changed during core uninstall.'
        }
        if (-not (Test-Path -LiteralPath $readyPath -PathType Leaf)) {
            throw 'Shared Nordic ready state was removed by core uninstall.'
        }
        if ($readyHashBefore -ne (Get-FileHash -LiteralPath $readyPath -Algorithm SHA256).Hash) {
            throw 'Shared Nordic ready state changed during core uninstall.'
        }
        return [pscustomobject][ordered]@{
            shared_ncs_preserved = $true
            ready_state_preserved = $true
            core_was_installed = $coreAbsence.core_was_installed
            uninstall_invoked = $coreAbsence.uninstall_invoked
            recovered_after_prior_uninstall = $coreAbsence.recovered_after_prior_uninstall
        }
    } | Out-Null

    Invoke-Step -Name 'reinstall_latest' -Action {
        $verified = Install-CoreVersion -Version $script:LatestVersion
        $reinstallBuildPath = Join-Path $script:BuildRoot 'blink-reinstalled'
        $compiled = Invoke-Compile -Label 'blink-reinstalled-compile' -BuildPath $reinstallBuildPath
        return [pscustomobject][ordered]@{
            nordic = $verified
            compile = $compiled
        }
    } | Out-Null

    $script:RunStatus = 'passed'
    Save-State
    Save-Evidence
    Add-RunLog -Text 'M10 TARGET RUN PASS'
    Exit-RunMutex -Handle $script:RunMutexHandle
    exit 0
} catch {
    $script:RunStatus = 'failed'
    Save-State
    Save-Evidence -Failure $_.Exception.Message
    Add-RunLog -Text ("M10 TARGET RUN FAIL: {0}" -f $_.Exception.Message)
    Exit-RunMutex -Handle $script:RunMutexHandle
    exit 1
}
