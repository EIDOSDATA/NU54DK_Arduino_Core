# HOST-W06 H11 Windows·macOS 통과와 Linux source 진단

기록일: 2026-11-10. Host 완료5/8, HOST-W06 진행 중이다.
Exact H11은 `c413fb238b93074c3c0465f527635ab2856d3f77`이다.
[320번](320_HOST_W06_H10_POSIX_Blink_통과와_Windows_mode_교정.md)의 Windows SDK Git mode 교정 이후 결과다.

## H11 실제 종료 결과

[Package CI42792855864](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/42792855864)는
producer·Windows smoke·macOS smoke 성공, Linux smoke 실패로 종료했다.

| 실제 Host | 설치·204예제 발견 | Blink·실제 artifact 검증 |
| --- | --- | --- |
| Windows x86-64 | PASS | PASS |
| macOS Apple Silicon | PASS | PASS |
| Ubuntu AMD64 | NOT_RUN | 설치 전 exact-source guard FAIL |

Windows/macOS의 원형 ELF·HEX·manifest·compile log를 독립 재검증했다(`666ff6/exit0`).
두 ARM load SHA-256은 `6eca127e7863bfc3bd7cfa073594be970d2efb2d9fab9a745e89b25bb3a30e71`이며
할당 section·정규화 HEX·memory region/budget·금지 symbol이 같았다. FLASH81,572B/RAM29,439B다.
Windows mode 교정은 이 source의 실제 설치·Blink PASS로 확인했다. 원형 전체 파일 hash도 보존한다.

| 원형 artifact | ID | ZIP SHA-256 |
| --- | --- | --- |
| Windows PASS | 13752249348 | `11b1c8d865f6961e6f67b102b7959b89c645adef839bf697e969d5a1c3171fec` |
| macOS PASS | 13753262706 | `7e1f55d68c085106b733f61a2829135c238776aafefda917b607135853a9deba` |
| Linux FAIL | 13753356447 | `3fbe16a935fab0ec97aa2d8281c6ec9c0abd291757a5d4ebf5bf6e394ce4f8ad` |

전체 ZIP의 source·size·원격 digest를 대조했다. 정본은
`D:/w06/control/host-w06-h11-smoke-audit-20261110.json`이다.
H10 Ubuntu PASS를 H11 Linux 칸에 합치지 않는다. 세 OS 전체 gate는 FAIL이고
204예제 compile/OS·9개 profile 거부/OS·세 OS 최종 비교는 `NOT_RUN`이다.
H11 prerequisite CI42792855191은 별도로3OS 성공했다. Software/build-only는 별도 종료 관찰을 따른다.

## Linux 원인 확인에 필요한 진단

원형 오류는 `native consumer는 exact clean CI source를 요구합니다.`다. 실제 HEAD 불일치,
GitHub SHA 불일치, 작업본 변경 중 어떤 조건인지 기록되지 않아 세부 원인은 **미확정**이다.
SDK 설치 전 거부이므로 Windows mode 수정이나 target firmware 오류로 분류하지 않는다.
H7 producer의 source guard FAIL도 세부 원인 미확정으로 원형을 보존한다.

H12에서는 기존 exact-source 판정 조건을 유지하고 다음 사실을 별도 기록한다.

- cache 복구 전과 consumer 종료 뒤 실제 HEAD·요청 SHA·GitHub SHA·repo 경로·tracked/untracked 경로
- consumer 진입 시 같은 사실과 board submodule 상태, source 거부 시 상세 JSON
- Git 경로 환경 변수의 경로 값만 기록하며 인증정보는 기록하지 않음

진단 artifact는 `host-source-*`로 분리한다. 기존 결과 artifact의 상대 경로·집계 분모는 유지한다.
변경 경로를 무시하거나 reset/clean으로 숨기지 않는다. cache가 원인이라고 선결론 내리지 않는다.
현재 source 진단 CLI의 exit0은 수집 성공이며 build PASS가 아니다.
로컬 실제 Git fixture에서 clean/HEAD 불일치/tracked 변경/untracked 추가를 구분했다.
관련 계약37개 중36PASS·조건부 SKIP1(`ef8fe3/exit0`), 실제 dirty 작업본4경로 수집은
`d25273/exit0`이다. 교정 source의 fresh native CI가 필요하며 이전 PASS를 이월하지 않는다.

## 보존과 다음 순서

SDK당 compile1·Ninja2·8shard/OS, 전체204예제/OS·거부9개/OS와 실제 image 비교 기준을 유지한다.
기존 W06 S19 actual PASS46·명시 수락 #29·40·44·원형 FAIL·soak·private11831·public3·완료 TODO6은 동결한다.
#29 원인 분석은 사용자 지시로 유예하며 새 HIL은0이다. w06 PAUSED 요청 유지·예약 생성/재활성화 없음.
HOST-W06 실제 전체 검증 뒤 HOST-W07 준비·Windows 회귀·RC1·사용자 Ubuntu/macOS 물리 gate 순으로 진행한다.
물리 USB·Serial·debug·lifecycle gate는 `NOT_RUN`이며 공개·정식 다중 OS 지원 완료를 뜻하지 않는다.
