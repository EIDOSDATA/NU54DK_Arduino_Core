# Repository work handoff

For v0.4.0 implementation, verification, documentation, or release work:

1. Before taking task actions, read `00_Docs/TODO_v0.4.0.md` completely, including its
   resume checkpoint, and follow its links to the applicable contracts and evidence.
2. For refactoring or any change covered by R00-R14, also read
   `00_Docs/01_아두이노 코어 설계/14_리팩토링/README.md` and the active
   `05_리팩토링_진행_체크리스트.md`. Keep the R item linked to the existing T/M gate;
   refactoring completion never substitutes for physical or release evidence.
3. Respect the latest user request. The TODO is a work plan, not blanket permission
   to flash a board, change wiring, publish a release, or delete files.
4. Select the relevant T01–T25 and R00-R14 item and record the intended scope before implementation.
   Update the checkpoint and evidence links before handing off or ending work.
5. Do not turn a build, mock/Host test, or scope decision into a physical PASS.
   Preserve existing public assets and historical evidence.
6. Keep the TODO while work remains. Archive or remove it only under its retention
   conditions, updating this entry point and incoming links in the same change.

## First-party C/C++ style

Use Korean Doxygen comments, BSD/Allman braces, four-space indentation and tab width.
Control-flow bodies require braces even for one statement. Preserve third-party code,
SDKs, board submodules and public release assets. Follow `.clang-format` and
`tools/format/README.md`. The active TODO records the user-requested final formatting
and regression gate before the next final commit/push.
