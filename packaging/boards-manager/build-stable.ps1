<#
.SYNOPSIS
NU54DK Boards Manager 정식 archive와 stable index를 생성합니다.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('0.1.0')]
    [string]$Version,

    [string]$Commit = 'v0.1.0',

    [string]$OutputDirectory = (Join-Path $PSScriptRoot 'out'),

    [string]$Python = 'python'
)

$ErrorActionPreference = 'Stop'
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Builder = Join-Path $PSScriptRoot 'nu54_package.py'

& $Python $Builder build `
    --repo-root $RepositoryRoot `
    --output-dir $OutputDirectory `
    --version $Version `
    --commit $Commit `
    --update-index

if ($LASTEXITCODE -ne 0) {
    throw "NU54DK stable package 생성이 실패했습니다. 종료 코드: $LASTEXITCODE"
}
