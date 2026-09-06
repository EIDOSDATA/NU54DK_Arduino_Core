$ErrorActionPreference = 'Stop'
$repoPath = 'C:\Users\eidos\GitHub\NU54DK_Arduino_Core'
$workPath = 'C:\Users\eidos\Documents\Codex\2026-09-06\new-chat\work'
$head = (& git -C $repoPath rev-parse HEAD).Trim()
$remote = (& git -C $repoPath rev-parse origin/main).Trim()
$branch = (& git -C $repoPath branch --show-current).Trim()
$status = @(& git -C $repoPath status --porcelain)
$distance = (& git -C $repoPath rev-list --left-right --count HEAD...origin/main).Trim()
if ($head -ne $remote -or $branch -ne 'main' -or $status.Count -ne 0 -or $distance -notmatch '^0\s+0$') { throw 'Final Git identity/clean check failed' }
$remoteUrl = (& git -C $repoPath remote get-url origin).Trim()
if ($remoteUrl -ne 'https://github.com/EIDOSDATA/NU54DK_Arduino_Core.git') { throw 'Unexpected origin URL' }
$worktrees = @(& git -C $repoPath worktree list --porcelain)
if (@($worktrees | Where-Object { $_ -like 'worktree *' }).Count -ne 1) { throw 'Unexpected worktree remains' }
$localBranches = @(& git -C $repoPath for-each-ref '--format=%(refname:short)' refs/heads)
if ($localBranches.Count -ne 1 -or $localBranches[0] -ne 'main') { throw 'Unexpected local branch remains' }
$workerName = '^(python|pythonw|arduino-cli|west|ninja|cmake|ccache|cc1|cc1plus|arm-zephyr-eabi-[^ ]+|qemu[^ ]*)\.exe$'
$taskPath = [regex]::Escape($workPath) + '|C:[\\/]r(?:0[0-9]|1[0-3]|[0-9])(?:[a-z][a-z0-9]*)?(?=[\\/\s"'']|$)'
$taskPath += '|C:[\\/]u2[a-z](?=[\\/\s"'']|$)'
$workers = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -match $workerName -and $_.CommandLine -match $taskPath } | Select-Object ProcessId,Name)
if ($workers.Count -ne 0) { $workers | Format-Table; throw 'Task build/runtime processes still exist' }
$sdkRecords = @()
foreach ($sdkPath in @('C:\ncs\v3.4.0\nrf','C:\ncs\v3.4.0\zephyr','C:\Users\eidos\ncs\v3.4.0\nrf','C:\Users\eidos\ncs\v3.4.0\zephyr')) {
    $sdkStatus = @(& git -C $sdkPath status --porcelain --untracked-files=no)
    if ($sdkStatus.Count -ne 0) { throw ('SDK tracked worktree changed: ' + $sdkPath) }
    $sdkRecords += @{ path=$sdkPath; revision=(& git -C $sdkPath rev-parse HEAD).Trim(); tracked_worktree_clean=$true }
}
$boardPath = Join-Path $repoPath 'board_package\NU54DK_Zephyr_DTS'
$boardStatus = @(& git -C $boardPath status --porcelain)
$boardRevision = (& git -C $boardPath rev-parse HEAD).Trim()
if ($boardStatus.Count -ne 0 -or $boardRevision -ne 'fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3') { throw 'Board identity/clean check failed' }
$record = @{
    head=$head; origin_main=$remote; branch=$branch; origin_url=$remoteUrl;
    working_tree_clean=$true; ahead=0; behind=0; worktree_count=1; local_branches=$localBranches;
    own_running_process_count=0; own_running_processes=$workers;
    sdk=$sdkRecords; board_gitlink=$boardRevision; board_worktree_clean=$true;
    physical_executed=$true; checked_at_utc=[DateTime]::UtcNow.ToString('o')
}
$record | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $workPath 't09-connected\final-checks.json') -Encoding utf8
Write-Output 'FINAL_GIT_PROCESS_SDK_CHECK_PASS'

