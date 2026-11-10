# HOST-W05 경로·cache·lock 교정과 native 검증

기록일: 2026-11-10. 현재 Host 4/8, HOST-W05는 native 세 OS 검증 전이며 아직 완료가 아니다.
개발 기준 parent는 H4 `4988d8723b76171b7caacbe67afb17e48d925ea0`이다.
이 기록을 포함하는 W05 후보와 H4·S19의 실적을 구분한다.

## 구현과 원형 실패

상대 override를 CWD 기준 절대화하던 경로를 거부하고 OS별 기본 SDK/cache 경로를 분리했다.
실제 cache 쓰기·POSIX 소유권·mode 검사와 Host identity를 key에 추가했다. 실제 이름을 기준으로
case·Unicode·symlink containment를 처리하고 고정 bundle 밖의 환경 경로를 거부한다.
POSIX lock은 사용자 TMP와 무관한 위치에 두며 Windows의 기존 kernel mutex identity는 유지한다.
상세 계약은 [경로·권한·cache·lock](<../02_빌드 설계/13_Host_경로_권한_cache_lock.md>)을 따른다.

| 로컬 attempt | 실제 결과와 조치 |
| --- | --- |
| initial-focused-a001 | exit1. Windows에서 주입한 POSIX `Path`의 문자열 구분자가 잘못 해석됐다. lexical 검사 전 Path의 POSIX 표현을 사용하도록 교정 |
| initial-focused-a002 | exit0, 관련45개 통과 |
| focused-a001 | exit1. 중복 JSON key의 ValueError가 Adapter 오류로 감싸지지 않았다. fail-closed 오류 변환 교정 |
| focused-a002·a003 | 각각 exit0, 65개 중60 PASS·조건부 SKIP5 |
| focused-a004 시작 명령 | exit1. shell의 미정의 Python 변수로 시험이 시작되지 않았다. 제품 시험 FAIL로 합산하지 않음 |
| focused-a005 | 명시 Python 경로로 fresh 실행, exit0, 66개 중61 PASS·조건부 SKIP5. 실제 260자 초과 한글·공백 경로의 atomic 파일·lock 추가 검증 포함 |

원본 로그·실제 tool 종료는 `D:/w06/control/host-w05-*`에 보존한다. 원형 실패를 후속 PASS로 덮어쓰지 않는다.

## 전체 로컬 회귀

W05 full-host-a001은 native8209, 실제 completion `a044ab/exit0`으로 종료했다.
268개 unittest 묶음에서 보고한 시험 합계는2,410개, 조건부 SKIP8이다. 시작 시 고정한 코드·시험·
설정2,439개 SHA-256이 종료 후 모두 일치했다. 이 전체 회귀 이후 추가한 긴 경로 시험은 focused-a005에서
검증했으며 전체 회귀를 다시 수행했다고 기록하지 않는다. firmware 제품 코드와 HIL은 바꾸지 않았다.

비공개 완료 receipt는 `D:/w06/control/host-w05-full-host-a001-completion.json`, 로그 SHA-256은
`e05bac6dc1aca552fd803ac4797188d90ac89718c463dff0fff54734326e9de7`이다.
현재 Windows의 POSIX mode·read-only·FIFO 등과 case-sensitive filesystem 조건은 SKIP으로 구분하고
실제 Ubuntu/macOS native CI에서 검증한다. 로컬 descriptor 주입을 해당 OS 실행으로 합산하지 않는다.

## source별 CI와 다음 단계

H4의 native SDK3/3, software9/9, build-only6/6 완료는 [313번](313_HOST_W04_설치_마감과_HOST_W05_경로_cache_lock_착수.md)에
기록했다. 이 결과를 W05 후보에 옮기지 않는다. W05를 고정한 fresh source의 세 OS 검사·SDK 재검증과
공통 software CI를 관찰하고 실제 실패가 있으면 원본 보존 후 필요한 교정과 새 source에서 검증한다.

W05가 완료된 뒤 HOST-W06 package/bootstrap·전체 예제 compile·산출물 비교 → W07 도구·Windows 회귀 →
M33-W07 RC1 준비 → 사용자 Ubuntu/macOS 실제 설치·USB·serial·debug·lifecycle → HOST-W08 순서로 진행한다.
추가 OS 실물 gate는 `NOT_RUN`이고 공개 승인은 별도다.

W06 S19의 실제 PASS46 + 명시 수락 #29·40·44, 원형 FAIL과 source/attempt 경계는 그대로다.
#29 원인 분석은 사용자 지시로 유예했고 새 HIL을 실행하지 않았다. w06 자동점검 PAUSED 요청을 유지하며
예약작업 생성·재활성화는 수행하지 않았다.
