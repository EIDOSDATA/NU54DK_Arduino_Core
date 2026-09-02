<#
.SYNOPSIS
NU54DK Boards Manager 정식 archive와 stable index를 생성합니다.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('0.1.0', '0.2.0', '0.3.0')]
    [string]$Version,

    [string]$Commit = '',

    [string]$OutputDirectory = (Join-Path $PSScriptRoot 'out'),

    [string]$Python = 'python'
)

$ErrorActionPreference = 'Stop'
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Builder = Join-Path $PSScriptRoot 'nu54_package.py'

if (-not $Commit) {
    $Commit = "v$Version"
}

& $Python $Builder build `
    --repo-root $RepositoryRoot `
    --output-dir $OutputDirectory `
    --version $Version `
    --commit $Commit

if ($LASTEXITCODE -ne 0) {
    throw "NU54DK stable package 생성이 실패했습니다. 종료 코드: $LASTEXITCODE"
}

$IndexArguments = @($Version)
if ($Version -in @('0.2.0', '0.3.0')) {
    $PriorArchive = Join-Path $OutputDirectory 'nucode-nu54dk-zephyr-0.1.0.zip'
    if (-not (Test-Path -LiteralPath $PriorArchive -PathType Leaf)) {
        throw "v$Version stable index에는 불변 v0.1.0 archive가 필요합니다: $PriorArchive"
    }
    $IndexArguments = @('0.2.0', '0.1.0')
}

if ($Version -eq '0.3.0') {
    $PriorArchive = Join-Path $OutputDirectory 'nucode-nu54dk-zephyr-0.2.0.zip'
    if (-not (Test-Path -LiteralPath $PriorArchive -PathType Leaf)) {
        throw "v0.3.0 stable index에는 불변 v0.2.0 archive가 필요합니다: $PriorArchive"
    }
    $IndexArguments = @('0.3.0', '0.2.0', '0.1.0')
}

& $Python $Builder index `
    --output-dir $OutputDirectory `
    --versions $IndexArguments `
    --output (Join-Path $OutputDirectory 'package_nucode_nu54dk_index.json')

if ($LASTEXITCODE -ne 0) {
    throw "NU54DK stable index 생성이 실패했습니다. 종료 코드: $LASTEXITCODE"
}
