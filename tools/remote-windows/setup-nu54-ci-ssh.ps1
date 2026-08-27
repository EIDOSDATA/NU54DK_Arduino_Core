<#
.SYNOPSIS
NU54DK clean Windows 검증기용 OpenSSH Server를 구성합니다.

.DESCRIPTION
전용 표준 로컬 사용자 생성, OpenSSH Server 설치, 공개키 등록, ACL 설정,
sshd_config 보강, 방화벽 제한, 서비스 시작 및 clean-machine 사전 진단을 수행합니다.

.PARAMETER UserName
원격 자동화에 사용할 표준 로컬 사용자 이름입니다.

.PARAMETER PublicKeyPath
개발 PC에서 생성한 OpenSSH 공개키(.pub)를 대상 PC에 복사한 경로입니다.

.PARAMETER PublicKey
PublicKeyPath 대신 직접 전달할 OpenSSH 공개키 한 줄입니다.

.PARAMETER AllowedRemoteAddress
SSH 방화벽 규칙이 허용할 원격 주소입니다. 기본값은 LocalSubnet입니다.

.PARAMETER KeepPasswordAuthentication
지정하면 SSH 암호 로그인을 유지합니다. 기본 동작은 공개키 등록 후 암호 로그인을 끄는 것입니다.

.PARAMETER GenerateAccountPassword
새 전용 계정의 임의 암호를 내부에서 생성합니다. 암호는 저장하거나 출력하지 않습니다.

.EXAMPLE
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup-nu54-ci-ssh.ps1 `
    -PublicKeyPath E:\nu54dk_m10_ed25519.pub

.EXAMPLE
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup-nu54-ci-ssh.ps1 `
    -PublicKeyPath E:\nu54dk_m10_ed25519.pub `
    -AllowedRemoteAddress 192.168.0.100
#>

[CmdletBinding()]
param(
    [Parameter()]
    [ValidatePattern('^[A-Za-z0-9_-]{1,20}$')]
    [string]$UserName = 'nu54ci',

    [Parameter()]
    [string]$PublicKeyPath,

    [Parameter()]
    [string]$PublicKey,

    [Parameter()]
    [ValidateNotNullOrEmpty()]
    [string]$AllowedRemoteAddress = 'LocalSubnet',

    [Parameter()]
    [switch]$KeepPasswordAuthentication,

    [Parameter()]
    [switch]$GenerateAccountPassword
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

## @brief 단계별 실행 상태를 일정한 형식으로 출력합니다.
function Write-Step {
    param(
        [Parameter(Mandatory)]
        [string]$Message
    )

    Write-Host "`n[NU54-SSH] $Message" -ForegroundColor Cyan
}

## @brief 현재 PowerShell이 관리자 권한으로 실행 중인지 확인합니다.
function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

## @brief UTF-8 BOM 없이 텍스트 파일을 기록합니다.
function Write-Utf8WithoutBom {
    param(
        [Parameter(Mandatory)]
        [string]$Path,

        [Parameter(Mandatory)]
        [AllowEmptyString()]
        [string]$Content
    )

    $encoding = [Text.UTF8Encoding]::new($false)
    [IO.File]::WriteAllText($Path, $Content, $encoding)
}

## @brief OpenSSH 공개키 입력을 읽고 단일 ED25519 공개키인지 검증합니다.
function Resolve-PublicKey {
    param(
        [string]$KeyPath,
        [string]$KeyText
    )

    if ($KeyPath -and $KeyText) {
        throw 'PublicKeyPath와 PublicKey는 동시에 지정할 수 없습니다.'
    }

    if ($KeyPath) {
        $resolvedPath = (Resolve-Path -LiteralPath $KeyPath).Path
        $KeyText = Get-Content -LiteralPath $resolvedPath -Raw -Encoding UTF8
    }

    if (-not $KeyText) {
        $KeyText = Read-Host '개발 PC에서 생성한 ssh-ed25519 공개키 한 줄을 붙여넣으십시오'
    }

    $keyLines = @(
        $KeyText -split "`r?`n" |
            ForEach-Object { $_.Trim() } |
            Where-Object { $_ }
    )

    if ($keyLines.Count -ne 1) {
        throw '공개키 입력에는 비어 있지 않은 한 줄만 있어야 합니다.'
    }

    $key = $keyLines[0]
    if ($key -notmatch '^ssh-ed25519\s+[A-Za-z0-9+/]+={0,3}(?:\s+.*)?$') {
        throw 'ssh-ed25519 형식의 공개키가 아닙니다. private key를 입력하지 마십시오.'
    }

    return $key
}

## @brief 로컬 사용자의 실제 프로필 경로를 SID로 찾습니다.
function Get-ProfilePathBySid {
    param(
        [Parameter(Mandatory)]
        [string]$Sid
    )

    $profile = Get-CimInstance -ClassName Win32_UserProfile |
        Where-Object { $_.SID -eq $Sid } |
        Select-Object -First 1

    if ($null -eq $profile) {
        return $null
    }

    return $profile.LocalPath
}

## @brief Windows Userenv API를 사용해 로컬 사용자의 프로필을 생성합니다.
function Initialize-UserProfile {
    param(
        [Parameter(Mandatory)]
        [string]$Sid,

        [Parameter(Mandatory)]
        [string]$UserName
    )

    if (-not ('Nu54dk.UserEnvNativeMethods' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;

namespace Nu54dk
{
    public static class UserEnvNativeMethods
    {
        [DllImport("userenv.dll", EntryPoint = "CreateProfile", CharSet = CharSet.Unicode, ExactSpelling = true)]
        public static extern int CreateProfile(
            string userSid,
            string userName,
            StringBuilder profilePath,
            uint profilePathLength);
    }
}
'@
    }

    $profilePathBuffer = [Text.StringBuilder]::new(260)
    $hresult = [Nu54dk.UserEnvNativeMethods]::CreateProfile(
        $Sid,
        $UserName,
        $profilePathBuffer,
        [uint32]$profilePathBuffer.Capacity
    )

    if ($hresult -eq 0) {
        return $profilePathBuffer.ToString()
    }

    $existingProfilePath = Get-ProfilePathBySid -Sid $Sid
    if ($existingProfilePath) {
        return $existingProfilePath
    }

    $hresultHex = [Convert]::ToString($hresult, 16).PadLeft(8, '0')
    $hresultException = [Runtime.InteropServices.Marshal]::GetExceptionForHR($hresult)
    throw "CreateProfile API 호출에 실패했습니다(HRESULT 0x$hresultHex): $($hresultException.Message)"
}

## @brief sshd_config의 Match 블록 앞 전역 지시자를 추가하거나 교체합니다.
function Set-SshdGlobalDirective {
    param(
        [Parameter(Mandatory)]
        [AllowEmptyString()]
        [string[]]$Lines,

        [Parameter(Mandatory)]
        [string]$Name,

        [Parameter(Mandatory)]
        [string]$Value,

        [switch]$MergeTokens
    )

    $matchIndex = $Lines.Count
    for ($index = 0; $index -lt $Lines.Count; $index++) {
        if ($Lines[$index] -match '^\s*Match\s+') {
            $matchIndex = $index
            break
        }
    }

    $globalLines = @()
    if ($matchIndex -gt 0) {
        $globalLines = @($Lines[0..($matchIndex - 1)])
    }

    $matchLines = @()
    if ($matchIndex -lt $Lines.Count) {
        $matchLines = @($Lines[$matchIndex..($Lines.Count - 1)])
    }

    $pattern = '^\s*' + [Regex]::Escape($Name) + '\s+(.+?)\s*$'
    $updatedGlobalLines = [Collections.Generic.List[string]]::new()
    $directiveWritten = $false

    foreach ($line in $globalLines) {
        if ($line -match $pattern) {
            if (-not $directiveWritten) {
                $directiveValue = $Value
                if ($MergeTokens) {
                    $tokens = @($Matches[1] -split '\s+' | Where-Object { $_ })
                    if ($tokens -notcontains $Value) {
                        $tokens += $Value
                    }
                    $directiveValue = $tokens -join ' '
                }

                $updatedGlobalLines.Add("$Name $directiveValue")
                $directiveWritten = $true
            }
            continue
        }

        $updatedGlobalLines.Add($line)
    }

    if (-not $directiveWritten) {
        $updatedGlobalLines.Add("$Name $Value")
    }

    $result = @($updatedGlobalLines)
    if ($matchLines.Count -gt 0) {
        if ($result.Count -gt 0 -and $result[-1] -ne '') {
            $result += ''
        }
        $result += $matchLines
    }

    return $result
}

## @brief icacls 실행 결과를 확인하고 실패하면 즉시 중단합니다.
function Invoke-Icacls {
    param(
        [Parameter(Mandatory)]
        [string[]]$Arguments
    )

    $icaclsExecutable = Join-Path $env:SystemRoot 'System32\icacls.exe'
    $global:LASTEXITCODE = 0
    & $icaclsExecutable @Arguments
    $nativeExitCode = $global:LASTEXITCODE
    if ($nativeExitCode -ne 0) {
        throw "icacls가 종료 코드 $nativeExitCode로 실패했습니다."
    }
}

if ($env:OS -ne 'Windows_NT') {
    throw '이 스크립트는 Windows 10 또는 Windows 11에서만 실행할 수 있습니다.'
}

if (-not (Test-IsAdministrator)) {
    throw 'PowerShell을 관리자 권한으로 실행한 뒤 이 스크립트를 다시 실행하십시오.'
}

$resolvedPublicKey = Resolve-PublicKey -KeyPath $PublicKeyPath -KeyText $PublicKey
$openSshCapabilityName = 'OpenSSH.Server~~~~0.0.1.0'
$firewallRuleName = 'OpenSSH-Server-In-TCP'
$sshdConfigPath = Join-Path $env:ProgramData 'ssh\sshd_config'
$sshdExecutable = Join-Path $env:WINDIR 'System32\OpenSSH\sshd.exe'
$accountPassword = $null
$accountCreated = $false

Write-Step '전용 표준 로컬 사용자를 확인합니다.'
$localUser = Get-LocalUser -Name $UserName -ErrorAction SilentlyContinue
if ($null -eq $localUser) {
    if ($GenerateAccountPassword) {
        $generatedPassword = ([Guid]::NewGuid().ToString('N') + 'aA9!')
        $accountPassword = ConvertTo-SecureString $generatedPassword -AsPlainText -Force
        $generatedPassword = $null
        Write-Host '전용 계정의 임의 암호를 내부에서 생성했습니다. SSH는 공개키 인증만 사용합니다.'
    } else {
        $accountPassword = Read-Host "새 로컬 사용자 '$UserName'의 강력한 암호를 입력하십시오" -AsSecureString
    }
    $localUser = New-LocalUser `
        -Name $UserName `
        -Password $accountPassword `
        -AccountNeverExpires `
        -PasswordNeverExpires `
        -Description 'NU54DK clean Windows 자동 검증 전용 계정'
    $accountCreated = $true
    Write-Host "표준 로컬 사용자 '$UserName'을 생성했습니다."
} else {
    Write-Host "기존 로컬 사용자 '$UserName'을 사용합니다."
}

$userSid = $localUser.SID.Value
$administratorsSid = [Security.Principal.SecurityIdentifier]::new('S-1-5-32-544')
$administratorMembers = @(Get-LocalGroupMember -SID $administratorsSid -ErrorAction SilentlyContinue)
if ($administratorMembers.SID.Value -contains $userSid) {
    throw "'$UserName'은 관리자 그룹 구성원입니다. 표준 사용자로 변경하거나 다른 이름을 사용하십시오."
}

$usersSid = [Security.Principal.SecurityIdentifier]::new('S-1-5-32-545')
$userMembers = @(Get-LocalGroupMember -SID $usersSid -ErrorAction SilentlyContinue)
if ($userMembers.SID.Value -notcontains $userSid) {
    Add-LocalGroupMember -SID $usersSid -Member "$env:COMPUTERNAME\$UserName"
}

Write-Step '사용자 프로필을 확인합니다.'
$profilePath = Get-ProfilePathBySid -Sid $userSid
if (-not $profilePath) {
    try {
        $profilePath = Initialize-UserProfile `
            -Sid $userSid `
            -UserName $UserName
    } catch {
        throw "'$UserName' 프로필을 만들지 못했습니다. 원인: $($_.Exception.Message)"
    }

    for ($attempt = 0; $attempt -lt 20 -and -not $profilePath; $attempt++) {
        Start-Sleep -Milliseconds 250
        $profilePath = Get-ProfilePathBySid -Sid $userSid
    }
}

if (-not $profilePath) {
    throw "'$UserName'의 Windows 프로필 경로를 확인하지 못했습니다. 해당 사용자로 한 번 로그인한 뒤 다시 실행하십시오."
}
Write-Host "사용자 프로필: $profilePath"

Write-Step 'OpenSSH Server를 설치하고 서비스를 시작합니다.'
$capability = Get-WindowsCapability -Online -Name $openSshCapabilityName
if ($capability.State -eq 'NotPresent') {
    Add-WindowsCapability -Online -Name $openSshCapabilityName | Out-Host
    $capability = Get-WindowsCapability -Online -Name $openSshCapabilityName
}

if ($capability.State -ne 'Installed') {
    throw "OpenSSH Server 설치 상태가 Installed가 아닙니다: $($capability.State)"
}

Set-Service -Name sshd -StartupType Automatic
Start-Service -Name sshd

if (-not (Test-Path -LiteralPath $sshdConfigPath)) {
    throw "sshd_config를 찾지 못했습니다: $sshdConfigPath"
}

Write-Step '사용자 공개키와 ACL을 설정합니다.'
$sshDirectory = Join-Path $profilePath '.ssh'
$authorizedKeysPath = Join-Path $sshDirectory 'authorized_keys'
New-Item -ItemType Directory -Path $sshDirectory -Force | Out-Null

Invoke-Icacls -Arguments @(
    $sshDirectory,
    '/inheritance:r',
    '/grant:r',
    "*${userSid}:(OI)(CI)F",
    '*S-1-5-18:(OI)(CI)F',
    '*S-1-5-32-544:(OI)(CI)F'
)

$authorizedKeys = @()
if (Test-Path -LiteralPath $authorizedKeysPath) {
    $authorizedKeys = @(
        Get-Content -LiteralPath $authorizedKeysPath -Encoding UTF8 |
            ForEach-Object { $_.Trim() } |
            Where-Object { $_ }
    )
}

if ($authorizedKeys -notcontains $resolvedPublicKey) {
    $authorizedKeys += $resolvedPublicKey
}

Write-Utf8WithoutBom `
    -Path $authorizedKeysPath `
    -Content (($authorizedKeys -join "`r`n") + "`r`n")

Invoke-Icacls -Arguments @(
    $authorizedKeysPath,
    '/inheritance:r',
    '/grant:r',
    "*${userSid}:F",
    '*S-1-5-18:F',
    '*S-1-5-32-544:F'
)

Write-Step 'sshd_config를 안전하게 갱신합니다.'
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$sshdConfigBackup = "$sshdConfigPath.$timestamp.bak"
Copy-Item -LiteralPath $sshdConfigPath -Destination $sshdConfigBackup

$sshdConfigLines = @(Get-Content -LiteralPath $sshdConfigPath -Encoding UTF8)
$sshdConfigLines = @(
    Set-SshdGlobalDirective `
        -Lines $sshdConfigLines `
        -Name 'PubkeyAuthentication' `
        -Value 'yes'
)
$sshdConfigLines = @(
    Set-SshdGlobalDirective `
        -Lines $sshdConfigLines `
        -Name 'PermitEmptyPasswords' `
        -Value 'no'
)
$sshdConfigLines = @(
    Set-SshdGlobalDirective `
        -Lines $sshdConfigLines `
        -Name 'AllowUsers' `
        -Value ($UserName.ToLowerInvariant()) `
        -MergeTokens
)

$passwordAuthentication = 'no'
if ($KeepPasswordAuthentication) {
    $passwordAuthentication = 'yes'
}
$sshdConfigLines = @(
    Set-SshdGlobalDirective `
        -Lines $sshdConfigLines `
        -Name 'PasswordAuthentication' `
        -Value $passwordAuthentication
)

Write-Utf8WithoutBom `
    -Path $sshdConfigPath `
    -Content (($sshdConfigLines -join "`r`n") + "`r`n")

$global:LASTEXITCODE = 0
$validationOutput = & $sshdExecutable -t 2>&1
$sshdValidationExitCode = $global:LASTEXITCODE
if ($sshdValidationExitCode -ne 0) {
    Copy-Item -LiteralPath $sshdConfigBackup -Destination $sshdConfigPath -Force
    throw "sshd_config 검증에 실패해 백업을 복원했습니다(종료 코드 $sshdValidationExitCode): $validationOutput"
}

Restart-Service -Name sshd

Write-Step 'SSH 방화벽 규칙을 제한된 주소로 구성합니다.'
$firewallRule = Get-NetFirewallRule -Name $firewallRuleName -ErrorAction SilentlyContinue
if ($null -eq $firewallRule) {
    New-NetFirewallRule `
        -Name $firewallRuleName `
        -DisplayName 'OpenSSH Server (sshd)' `
        -Enabled True `
        -Direction Inbound `
        -Protocol TCP `
        -Action Allow `
        -LocalPort 22 `
        -Profile Any `
        -RemoteAddress $AllowedRemoteAddress | Out-Null
} else {
    Set-NetFirewallRule `
        -Name $firewallRuleName `
        -Enabled True `
        -Direction Inbound `
        -Action Allow `
        -Protocol TCP `
        -LocalPort 22 `
        -Profile Any `
        -RemoteAddress $AllowedRemoteAddress | Out-Null
}

Write-Step '원격 시험 작업 디렉터리를 준비합니다.'
$runnerDirectory = Join-Path $profilePath 'NU54CI'
New-Item -ItemType Directory -Path $runnerDirectory -Force | Out-Null
Invoke-Icacls -Arguments @(
    $runnerDirectory,
    '/inheritance:r',
    '/grant:r',
    "*${userSid}:(OI)(CI)F",
    '*S-1-5-18:(OI)(CI)F',
    '*S-1-5-32-544:(OI)(CI)F'
)

Write-Step 'Clean Windows 사전 상태를 진단합니다.'
$unexpectedCommands = [Collections.Generic.List[string]]::new()
foreach ($commandName in @('git', 'python', 'cmake', 'ninja', 'west', 'pyocd')) {
    $command = Get-Command $commandName -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        $unexpectedCommands.Add("$commandName=$($command.Source)")
    }
}

$ncsExists = Test-Path -LiteralPath 'C:\ncs'
if ($unexpectedCommands.Count -gt 0) {
    Write-Warning "Clean 검증에 영향을 줄 수 있는 명령을 찾았습니다: $($unexpectedCommands -join ', ')"
}
if ($ncsExists) {
    Write-Warning 'C:\ncs가 존재합니다. 완전한 Boards Manager 설치 시험 전 별도 검토가 필요합니다.'
}

$ipv4Addresses = @(
    Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object {
            $_.IPAddress -ne '127.0.0.1' -and
            $_.IPAddress -notlike '169.254.*'
        } |
        Select-Object -ExpandProperty IPAddress -Unique
)

$hostKeyPath = Join-Path $env:ProgramData 'ssh\ssh_host_ed25519_key.pub'
$hostFingerprint = '확인할 수 없음'
if (Test-Path -LiteralPath $hostKeyPath) {
    $hostFingerprint = (& ssh-keygen.exe -lf $hostKeyPath 2>&1) -join ' '
}

Write-Step '설정이 완료되었습니다.'
Write-Host "컴퓨터 이름          : $env:COMPUTERNAME"
Write-Host "SSH 사용자           : $UserName"
Write-Host "IPv4 주소            : $($ipv4Addresses -join ', ')"
Write-Host "허용 원격 주소       : $AllowedRemoteAddress"
Write-Host "사용자 프로필        : $profilePath"
Write-Host "작업 디렉터리        : $runnerDirectory"
Write-Host "sshd_config 백업     : $sshdConfigBackup"
Write-Host "암호 SSH 로그인      : $passwordAuthentication"
Write-Host "OpenSSH host key     : $hostFingerprint"
Write-Host "C:\ncs 존재          : $ncsExists"
Write-Host "계정 신규 생성       : $accountCreated"
Write-Host ''
Write-Host '개발 PC에서 다음 형식으로 접속하십시오:' -ForegroundColor Green
Write-Host "ssh -i `$env:USERPROFILE\.ssh\nu54dk_m10_ed25519 $UserName@<위 IPv4 주소>"
Write-Host ''
Write-Host '인터넷 공유기의 22번 포트를 포워딩하지 마십시오. 같은 LAN 또는 VPN에서만 사용하십시오.' -ForegroundColor Yellow
