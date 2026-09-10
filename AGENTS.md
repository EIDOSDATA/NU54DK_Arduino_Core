# Repository work handoff

Owner-authorized exception (2026-09-08): retire public versions below v0.3.0 and
compact main history while preserving original evidence and assets on an archive branch.
Keep the v0.3.0 tag and payload unchanged; update its catalog only. See
[the retirement record](<00_Docs/04_검증 기록/106_Git_이력_정리와_구버전_패키지_공급_종료.md>).


For v0.4.0 implementation, verification, documentation, or release work:

1. Before taking task actions, read `00_Docs/TODO_v0.4.0.md` completely, including its
   resume checkpoint, and follow its links to the applicable contracts and evidence.
2. For refactoring or any change covered by R00-R14, also read
   `00_Docs/01_아두이노 코어 설계/14_리팩토링/README.md` and the active
   `05_리팩토링_진행_체크리스트.md`. Keep the R item linked to the existing T/M gate;
   refactoring completion never substitutes for physical or release evidence. The current v0.4.0
   order completes R00-R13 before the final current-source T11/T12-T15 physical campaign, then
   performs T16-T18, R14 and T19-T25. Do not reuse historical T11 PASS as the final-source result.
3. Respect the latest user request. The TODO is a work plan, not blanket permission
   to flash a board, change wiring, publish a release, or delete files.
4. Select the relevant T01–T25 and R00-R14 item and record the intended scope before implementation.
   Update the checkpoint and evidence links before handing off or ending work.
5. Do not turn a build, mock/Host test, or scope decision into a physical PASS.
   Preserve existing public assets and historical evidence.
6. Keep the TODO while work remains. Archive or remove it only under its retention
   conditions, updating this entry point and incoming links in the same change.

## Current T13 boundary

The owner excludes QDEC diagnostics and serial handover from this work. Read all documentation
before the requested documentation cleanup; then report that cleanup before hardware work.
For S resume, check the full GPIO harness first. The owner confirms the maintained wiring and
revokes arbitrary time-based reconfirmation expiry. Keep firmware watchdogs, command leases,
exclusive probe locks and STOP/pin-release checks. A fresh fault requires connectivity checks
and CMSIS-DAP diagnosis, not blind retries or an invented time-expiry blocker.
The requested S scope is closed (56 PASS plus 2 excluded peer-controlled System OFF conditions),
and U software/image preparation is complete. Do not restart completed S work from historical
instructions. The owner confirmed the minimal UARTE00 four-signal wiring; U physical execution is
in progress and must not be recorded as PASS before its actual results. The U checker tests only
those four connected signal nets, while the S checker retains its full 17-signal scope.
The owner removed the historical GPIO/SWD diagnostics from the current issue list, excluded
additional SPI early-CS slave-frame qualification, and accepted the completed 2 ms TWIS delay
tests without requiring separate read-request delay tests. Do not requeue those items or
promote the scope decisions to new physical PASS results. Preserve original evidence.
Issue documentation must put an explicit resolved status beside fixed problems and omit excluded
items from current issue and remaining-work tables. Keep historical results and restrictions
separate; pending validation is not a confirmed defect. The active TODO is the status index.
Every progress report must state the completed scope and percentage;
distinguish documentation progress from the S 58-condition physical denominator. See the active TODO
for counts and exact evidence.

## First-party C/C++ style

Use Korean Doxygen comments, BSD/Allman braces, four-space indentation and tab width.
Control-flow bodies require braces even for one statement. Preserve third-party code,
SDKs, board submodules and public release assets. Follow `.clang-format` and
`tools/format/README.md`. The active TODO records the user-requested final formatting
and regression gate before the next final commit/push.
