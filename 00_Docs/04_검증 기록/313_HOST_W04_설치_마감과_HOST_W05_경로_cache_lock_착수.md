# HOST-W04 설치 마감과 HOST-W05 경로·cache·lock 착수

기록일: 2026-11-10 · Host 완료4/8 · 현재 HOST-W05 진행 중.

HOST-W04의 OS별 prerequisite 설치·검증 범위는 source
`4988d8723b76171b7caacbe67afb17e48d925ea0`(H4)의
[native CI42751311805](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/42751311805)에서
Windows·Ubuntu·macOS 실제3/3, SKIP0으로 완료했다. 세 artifact의 ZIP digest·크기, source·manifest·
backend SHA-256, 실제 SDK/Zephyr revision과 고정 bundle ID, 도구 실행 결과 및 저장 상태 재검증을 대조했다.
H1·H2·H3의 원형 FAIL과 source별 성공 구성요소는 [312번](312_HOST_W04_최초_CI_실패와_교정_검증.md)에 보존하며
H4 결과로 소급 변경하지 않는다.

| Host | 고정 toolchain bundle | 실제 설치·재검증 |
| --- | --- | --- |
| Windows x86-64 | `dcbdc366a1` | PASS |
| Ubuntu AMD64 | `fbf7391cab` | PASS |
| macOS Apple Silicon | `ccc010f809` | PASS |

세 OS 모두 nRF Util core8.2.1, sdk-manager1.16.1, SDK v3.4.0과 exact NCS/Zephyr revision을 유지했다.
Python·west·compiler·size의 실제 실행 출력을 artifact에 기록했다.
비공개 `D:/w06/control/host-w04-h4-native-closure-20261110.json`이 설치 범위의 상세 대조 기록이다.
후속 관측에서 같은 H4의 [software CI42752228422](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/42752228422)는
9/9 성공했고 [build-only CI42751312030](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/42751312030)는
계획·4 shard·집계 6/6 성공으로 종료했다. H2·H3 및 원형 H1 실패와 source별로 구분한다.
이 build-only 성공은 S19의 실제 HIL 실적을 추가하거나 다시 판정하지 않는다. 전체 예제·Boards Manager bootstrap은 HOST-W06,
실제 USB·serial·debug·lifecycle은 RC1 최종 사용자 gate이며 아직 `NOT_RUN`이다. Host 전체8/8이나 추가 OS 정식 지원이 아니다.

2026-11-10 03:47 UTC에 W06 원본도 읽기 전용으로 다시 대조했다. S19 비공개11,831개 전체의 크기·
SHA-256, 공개3개, 완료 TODO6개가 일치했다. firmware core·library·template·HIL source는 S19 이후 변경되지 않았다.
기존 실제 PASS46 + 명시 수락 #29·40·44의 마감과 원형 FAIL을 보존한다. #29 원인 분석과 새 HIL은 수행하지 않는다.

W05는 명시 경로의 상대/다른 OS 경로 거부, XDG·Library·LocalAppData 기본값, cache 쓰기 권한·소유권,
Host별 cache identity와 case·symlink·공백·한글 경로, POSIX/Windows lock 배타성·timeout·회수 의미를 다룬다.
읽기 전용 검토에서 상대 override의 자동 절대화와 사용자 구분 없는 POSIX 임시 lock 경로를 확인했다.
관련 코드를 교정하고 실제 process·파일 권한 검사를 포함한 native 회귀로 검증한다. W05는 아직 완료하지 않았다.

현행 [Host 원장](../../variants/nu54dk/host-readiness.json)과
[다중 Host 계약](<../02_빌드 설계/10_v0.5.0_다중_Host_지원_착수_계약.md>)을 따른다.
후속 순서는 W05 → W06 package/native 전체 예제 CI → W07 도구·Windows 회귀 → M33-W07 RC1 →
사용자 Ubuntu/macOS 최종 실기 → HOST-W08 → M33-W08 별도 공개 승인이다.
