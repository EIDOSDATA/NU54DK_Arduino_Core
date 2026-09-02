<#
.SYNOPSIS
NU54DK Boards Manager preview archive와 index를 생성합니다.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('0.0.96', '0.0.97')]
    [string]$Version,

    [string]$Commit = 'HEAD',

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
    throw "NU54DK package 생성이 실패했습니다. 종료 코드: $LASTEXITCODE"
}
