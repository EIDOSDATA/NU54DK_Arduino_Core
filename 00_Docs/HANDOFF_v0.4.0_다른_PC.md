# v0.4.0 다른 PC 재개 인계

현재 작업·완료 수·제외 조건은 [TODO 전체](TODO_v0.4.0.md)가 기준입니다.
이 문서는 새 PC에서 저장소·도구·보드와 증거를 복원하는 절차를 설명합니다.

## 먼저 읽을 문서

1. [AGENTS.md](../AGENTS.md), [TODO](TODO_v0.4.0.md)
2. [113번 S 범위 종료와 U 준비](<04_검증 기록/113_T13_S_범위_종료와_U_준비.md>)
3. [114번 문서 정비와 남은 마일스톤](<04_검증 기록/114_전체_문서_정비와_남은_마일스톤.md>)
4. [115번 U 완료와 T13 종료](<04_검증 기록/115_T13_U_UART00_완료와_T13_종료.md>)
5. [116번 T14 자원 충돌 판정](<04_검증 기록/116_T14_자원_충돌_판정과_PWM_식별_교정.md>)
6. [117번 T15 지원 범위 확정](<04_검증 기록/117_T15_지원_범위와_Physical_Gate_확정.md>)
7. [118번 T16 설치 통합](<04_검증 기록/118_T16_Peripheral_Fabric_설치_통합.md>)
8. [119번 T17 문서와 지원 매트릭스](<04_검증 기록/119_T17_문서와_지원_매트릭스_정리.md>)
9. [120번 T18 stable 공개 절차와 승인 차단](<04_검증 기록/120_T18_stable_공개_절차와_승인_차단.md>)
10. [121번 T19 RC 소스 고정과 전체 회귀](<04_검증 기록/121_T19_RC_소스_고정과_전체_회귀.md>)
11. [122번 T20 RC 설치 수명주기와 실제 Upload](<04_검증 기록/122_T20_RC_설치_수명주기와_실제_Upload.md>)
12. [T13 계획·U 결선](../tests/hil/nu54dk/T13_PLAN.md)

과거 원인 분석은 위 문서가 연결하는 실행별 기록을 필요할 때 읽습니다. 예전 기록의
‘다음 실행’이나 PC 경로를 현재 재개 명령으로 가져오지 않습니다.

## 저장소와 도구 준비

원격은 `https://github.com/EIDOSDATA/NU54DK_Arduino_Core.git`, 브랜치는 `main`입니다.
과거 인계에 적힌 source로 checkout을 되돌리지 말고 현재 HEAD와 검증 image의 source를 각각 확인합니다.
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
현재 사용자가 유지 중이라고 확인한 결선에는 시간 만료를 적용하지 않습니다. 전체 GPIO 연결성을
먼저 검사하고 이상 발생 시 다시 확인합니다. 새 PC·새 결선에서는 달라진 USB/전원/배선을 실제로
대조하되, 시간이 지났다는 이유만으로 재확인을 요구하지 않습니다. Firmware watchdog과 명령
lease·STOP·배타 잠금은 유지합니다.

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
현재 PC의 격리 build와 source별 근거는 110번 이후 실행 기록에서 확인합니다.
로컬 상태 JSON에는 예전 집계와 만료 문구가 남아 있을 수 있으므로 최신 TODO·사용자 지시·실행별
원본을 함께 대조합니다. 상태 파일의 과거 `running` 표시만으로 실제 프로세스가 살아 있다고 판단하지 않습니다.

## 작업 경계

T12와 QDEC 문제 보고 후 검증 작업 완료는 유지합니다. QDEC 재진단, 연속 UART/SPI/TWI 역할 전환,
T13 peer 제어 System OFF 추가 결합 시험은 현재 범위에 포함하지 않습니다. S는 56 PASS와 2조건
제외를 구분해 종료했고 UARTE00도 별도 4-net 검사·정상 180초·flow 200회·취소 400회를
완료했습니다. [115번 완료 기록](<04_검증 기록/115_T13_U_UART00_완료와_T13_종료.md>)을 따르며
완료한 S/U 시험·C05 1시간 soak를 다시 예약하지 않습니다.
지원 범위·RC·정식 공개가 완료된 것은 아닙니다. 공개는 T22의 결과별 명시적 승인 이후입니다.

현재 `main`은 T16 `fabric` profile과 `NUCODE Peripheral Fabric` library를 포함합니다. v0.4 후보는
library 9개·예제 30개이고 v0.3 stable은 8개·29개입니다. T17 문서·지원 원장은 119번, T18 stable
준비·승인 차단 절차는 120번에서 완료했습니다. R14/T19 전체 software 회귀와 RC 이중 재현성은
121번, T20 Boards Manager 설치·30개 예제·Upload·전환·제거·재설치는 122번에서 완료했습니다.
재개 지점은 T21 비공개 stable 최종 검사입니다. T22 소유자 승인과
T23 공개 쓰기는 자동 진행 범위에 포함하지 않습니다.
