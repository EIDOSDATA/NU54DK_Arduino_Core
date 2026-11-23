# HOST-W06 native package 구현과 검증 착수

기록일: 2026-11-10. Host 완료5/8, 현재 HOST-W06 진행 중이다.
W05의 exact H5 source `2dd1455e771afdeab5a599874bf634659bf3b643`는
[315번](315_HOST_W05_native_마감과_HOST_W06_package_착수.md)에서 마감했다.
추가 관찰한 H5 [build-only CI42759627539](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/42759627539)도
실제6/6 성공·SKIP0으로 끝났다. H5 native3/3·software9/9와 별도로 기록하며 W06 HIL에 합산하지 않는다.

## 구현과 로컬 검증

초기 Python이 없어 post-install 자체를 시작할 수 없는 순환 의존성을 해소하기 위해 공식 고정
CPython runtime을 Boards Manager tool dependency로 추가했다. 실제 upstream asset의 hash·size와
세 OS별 notice 원문60개를 확보했다. Windows 초기 runtime은 부모 Python 환경을 제거한 실제 실행,
한글 파일 I/O와 TLS 인증서·hostname 검증을 켠 HTTPS를 통과했다(`bb967a/exit0`).

Native package는 같은 Git blob의 pin·notice·platform·backend를 선택하고 OS별 bundle map,
post-install과 네 builder recipe를 같은 bootstrap Python으로 결합한다. 기존 stable 0.5.0의
package·index·공개 allowlist는 그대로 보존한다. 구현 계약은
[native package 설계](<../02_빌드 설계/14_native_Boards_Manager_package와_CI.md>)를 따른다.

| 로컬 실행 | 실제 결과 | 판단과 보존 |
| --- | --- | --- |
| Package draft A001, snapshot `6c310705…` | `687a92/exit1` | Native SPDX 외부 의존19개를 기존7개로 판정하던 package 검증 코드 실패. 원형 보존 |
| Package draft A002, snapshot `85543b75…` | `07d716/exit1` | Archive·sidecar 재현/검증 뒤 private `-host.1` version 정렬 미지원으로 index 생성 실패. 원형 보존 |
| Package draft A003, snapshot `d9fb4e79…` | `2001d5/exit0` | 위 두 검증/정렬 문제 교정 후 fresh archive·sidecar 두 번 동일, archive/index 검증 성공 |
| Native package·기존 package focused·state root | `e39c6c/exit0` | 보고29개, PASS28·조건부 POSIX SKIP1 |
| Native package·consumer·artifact·집계 계약 | `70f16d/exit0` | 보고25개, PASS24·조건부 POSIX SKIP1 |

A001~A003은 실제 branch HEAD를 움직이지 않은 격리 Git snapshot의 개발 시험이다.
A003의 package ZIP SHA-256은 `206b2972fcab3242435f66ecb5fa42212bbbeb718383c947193ca0f7f2818185`,
index는 `3fb72d0db4fd29cf708ed11b81e0f5c2d7b1ae5836d5249f452ccc607af107e4`다.
`D:/w06/control/host-w06-native-package-draft-a00{1,2,3}` 아래 log·start·completion을 각각 보존한다.
이 개발 결과를 최종 커밋의 native 설치·전체 예제 CI 성공으로 옮기지 않는다.

기존 M10 전체 package suite 최초 실행(`8a0818/exit1`)은 21개 중20 PASS·1 ERROR였다.
오래된 공개0.2.0/RC2 비교에 필요한 과거 Git object 두 개가 현재 checkout에 없어 생긴 환경 오류다.
필요 object만 원격에서 읽어 확보했으며 HEAD·index·worktree를 바꾸지 않았다. 실패한 그1개를 fresh
집중 실행한 결과 `a1e61c/exit0`으로 통과했다. 이를 전체21개 fresh PASS로 합산하지 않는다.
최종 exact source의 공통 software CI에서 전체 package suite를 다시 판정한다.

## 다음 gate

현재 변경은 아직 최종 commit/native package CI를 실행하기 전이다. 실제 Boards Manager 설치,
세 OS의 예제204개씩·잘못된 profile9개씩과 artifact 비교는 `NOT_RUN`이다.
새 workflow는 실제 설치·Blink 비교가 모두 성공한 뒤24개 전체 예제 worker로 확대하며 FAIL을 자동 재시도하지 않는다.
최종 source를 고정하고 fresh native CI와 공통 software CI를 관찰·검증한 뒤에만 HOST-W06을 마감한다.

기존 W06 S19 원본은 실제 PASS46과 명시 수락 #29·40·44를 분리 보존한다. #29 분석·새 HIL은 하지 않았다.
완료 TODO6개·기존 source별 PASS/FAIL·공개 자산을 보존한다. 자동점검 w06 PAUSED 요청을 유지하고
예약작업은 생성/재활성화하지 않는다. Ubuntu/macOS 물리 USB·Serial·debug·lifecycle은 RC1 최종
사용자 gate `NOT_RUN`이며 Host8/8·정식 다중 OS 지원·공개 완료로 표시하지 않는다.

후속 H6 exact CI는 producer PASS·native package smoke3OS FAIL로 종료했다. 이 기록의 CI 미실행 문장은 착수 당시 snapshot이다. 실제 원인·교정과 원형 보존은 [317번](317_HOST_W06_H6_설치_FAIL_원인과_교정.md)을 따른다.
