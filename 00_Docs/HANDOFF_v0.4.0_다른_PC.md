# v0.4.0 다른 PC 재개 인계

현재 작업·완료 수·제외 조건은 [TODO 전체](TODO_v0.4.0.md)가 기준입니다.
이 문서는 새 PC에서 저장소·도구·보드와 증거를 복원하는 절차를 설명합니다.

## 먼저 읽을 문서

1. [AGENTS.md](../AGENTS.md), [TODO](TODO_v0.4.0.md)
2. [109번 최근 복구 결과와 연속 전환 제외](<04_검증 기록/109_T13_S_세_복구_묶음_재검증.md>)
3. [110번 문서 정리와 S 재개](<04_검증 기록/110_문서_정리와_T13_S_잔여_재개.md>)
4. [94번 PWM STOP 수정·인계 검증](<04_검증 기록/94_T14_PWM_지연_시작_취소와_무점퍼_검증.md>)과 [95번 ADC·TIMER·이벤트 검증](<04_검증 기록/95_T12_내부_ADC_TIMER_이벤트_무점퍼_검증.md>)

## 저장소와 도구 준비

원격은 `https://github.com/EIDOSDATA/NU54DK_Arduino_Core.git`, 브랜치는 `main`입니다.
이전 인계 시작 commit은 `f42bda55f7b45f7af0a347ecf5f1f516bb34eb6a`이며 최신 HEAD가 아닙니다.
이력 정리 전 source는 [106번 Git 정리 기록](<04_검증 기록/106_Git_이력_정리와_구버전_패키지_공급_종료.md>)의
archive 브랜치와 해당 evidence에서 찾습니다.

1. 실제 저장소를 찾고 미커밋 변경·현재 branch·HEAD·submodule을 확인합니다. 기존 변경을 보존합니다.
2. 깨끗한 main에서 fetch·fast-forward와 submodule 초기화를 진행합니다. 강제 reset/clean은 하지 않습니다.
3. [Windows 개발환경](<02_빌드 설계/09_Windows_개발환경_설정.md>)에 따라 없는 도구만 준비합니다.
4. 버전은 [CI lock](../tools/ci/ncs-3.4.0.lock.json)과 [prerequisite pins](../tools/nu54-prerequisites/pins.json)를 따릅니다.
5. Host와 target PATH를 분리합니다. Host compiler·linker를 실제 확인하고 고정 NCS CMake/Ninja를 사용합니다.
   Windows 실행 차단은 원본 오류로 기록하며 보안 정책을 우회하지 않습니다.
6. `python -B tools/ci/run_m12_gate.py <gate>`로 contract·docs·inventory·package·examples·host 중
   작업에 필요한 검사를 수행합니다. 이전 PC의 PASS를 새 환경의 결과로 사용하지 않습니다.

## 보드와 실기 재개

새 PC에서는 USB/probe를 열거하고 exact UID hash·role·image를 다시 대조합니다.
COM 번호나 USB 순서를 이전 PC에서 가져오지 않습니다. USB 열거·SWD 응답·펌웨어 READY는 별도 상태입니다.

외부 실기는 [T13 S/U GPIO 표](../tests/hil/nu54dk/T13_PLAN.md)를 기준으로 현재 결선을 확인합니다.
두 USB 분리→결선 변경→재연결, 동일 I/O 전압, 양쪽 DAP UART 분리/SWD 연결,
공통 GND·전원 레일 미연결·추가 출력/외부 풀업 미연결 조건을 유지합니다.
확인서의 범위·유효기간·변경 보고를 대조하고 새 campaign의 결선 checker를 통과한 뒤 출력합니다.

SWD10MHz·exact UID·배타 lock·sector flash·`auto_unlock=false`·controlled start를 사용합니다.
자동 mass erase/recover·임의 보드 전환은 하지 않습니다. 원시 UID나 인증 정보는 공개 기록에 넣지 않습니다.
STOP·clock·핀 반환이 확인되지 않으면 후속 실기를 시작하지 않습니다.

## 가져올 자료와 다시 만들 자료

| 자료 | 재개 방법 |
| --- | --- |
| 코드·문서·정규화 로그·raw 압축·SHA manifest | Git main과 검증 기록의 evidence에서 확인 |
| 이력 정리 전 source·공급 종료 자산 |106번 archive 근거에서 확인 |
| ELF/HEX·compile DB·SDK/build cache | 새 PC에서 exact source로 재생성. 이전 경로는 출처일 뿐 현재 경로가 아님 |
| 비공개 UID·실행 중 세션 정보 | 현재 PC에서 새로 식별. 공개 문서로 옮기지 않음 |

SDK `ready.json`과 절대 경로 cache를 복사해 설치 검증 완료로 간주하지 않습니다.
현재 PC의 격리 build와 source별 근거는110번 이후 실행 기록에서 확인합니다.

## 작업 경계

T12와 QDEC 문제 보고 후 검증 작업 완료는 유지합니다. QDEC 재진단과 연속 UART/SPI/TWI 역할 전환은
이번 자동 실행에 포함하지 않습니다. 현재 승인 범위는 문서 정리 후 S 순서1~3이며 U 변경은 별도 안내합니다.
지원 범위·RC·정식 공개가 완료된 것은 아닙니다. 공개는 T22의 결과별 명시적 승인 이후입니다.
