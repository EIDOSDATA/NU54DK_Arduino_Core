# v0.4.0 완료 상태와 다른 PC 개발 준비

**v0.4.0의 T01~T25는 모두 완료됐습니다.** 이 문서는 완료한 시험을 재개하라는 지시가 아니라,
다른 PC에서 후속 개발에 필요한 저장소·도구·증거를 찾는 안내입니다.

## 먼저 확인할 세 문서

1. [작업 지침](../AGENTS.md): 변경·검증·보존 원칙
2. [v0.4.0 완료 TODO](TODO_v0.4.0.md): 단계별 결과·해결 상태·지원 경계
3. [125번 정식 공개 기록](<04_검증 기록/125_v0.4.0_정식_릴리스_공개와_T24_T25_마감.md>): 최종 source·자산·T24/T25 결과

| 추가로 필요한 내용 | 찾아갈 곳 |
| --- | --- |
| QDEC20/21 최종 지원 계약 | [124번 지원 범위 재확정](<04_검증 기록/124_T22전_QDEC_지원_범위_재확정.md>) |
| T13 S/U 실제 시험과 종료 상태 | [113번 S 종료](<04_검증 기록/113_T13_S_범위_종료와_U_준비.md>) · [115번 U 종료](<04_검증 기록/115_T13_U_UART00_완료와_T13_종료.md>) |
| 특정 실패·수정·재검증의 원본 | [검증 기록 목차](<04_검증 기록/README.md>) |
| 설계·설치·API 탐색 | [문서 안내](README.md) |
| 후속 제품 개발 | [제품 로드맵](<01_아두이노 코어 설계/02_구현_로드맵.md>), [v0.5.0 착수 계획](TODO_v0.5.0.md)과 최신 사용자 요청 |

과거 기록의 “다음 실행”, `running` 표시, PC 절대 경로는 당시 상태입니다.
현재 명령·보드 연결·실행 중 프로세스의 근거로 사용하지 않습니다.

## 저장소와 도구 준비

원격은 `https://github.com/EIDOSDATA/NU54DK_Arduino_Core.git`, 기본 개발 브랜치는 `main`입니다.
정식 v0.4.0 tag source와 현재 main HEAD는 목적이 다르므로 각각 확인합니다.

1. 실제 저장소의 branch·HEAD·미커밋 변경·submodule을 확인하고 기존 변경을 보존합니다.
2. 새 복제는 `git clone --recurse-submodules`를 사용합니다. 기존 checkout에서는 작업 상태를 확인한 뒤
   fetch·fast-forward·submodule 초기화를 수행합니다. 강제 reset/clean은 하지 않습니다.
3. [Windows 개발환경](<02_빌드 설계/09_Windows_개발환경_설정.md>)에 따라 없는 도구만 준비합니다.
4. 버전은 [CI lock](../tools/ci/ncs-3.4.0.lock.json)과 [prerequisite pins](../tools/nu54-prerequisites/pins.json)를 따릅니다.
5. Host compiler·linker와 target PATH를 분리하고, 고정 NCS CMake/Ninja를 사용합니다.
   SDK 설치 상태 파일과 이전 PC 절대 경로 cache를 복사해 검증 완료로 간주하지 않습니다.
6. `python -B tools/ci/run_m12_gate.py <gate>`로 작업에 해당하는 contract·docs·inventory·package·examples·host
   검사를 수행합니다. 이전 PC의 PASS와 이번 실행 결과를 구분합니다.

일반 Arduino 사용자라면 위 개발 도구 대신 [Boards Manager 설치](<02_빌드 설계/06_Boards_Manager_설치와_패키징.md>)를 사용합니다.

## 보존 자료와 재생성 자료

| 자료 | 취급 방법 |
| --- | --- |
| 코드·문서·정규화 로그·raw 압축·SHA manifest | Git과 검증 기록의 evidence에서 확인·보존 |
| 이력 정리 전 source·공급 종료 자산 | [106번 archive 안내](<04_검증 기록/106_Git_이력_정리와_구버전_패키지_공급_종료.md>)에서 확인 |
| ELF/HEX·compile DB·SDK/build cache | 필요할 때 exact source로 재생성. 이전 로컬 경로가 현재 존재한다고 가정하지 않음 |
| Probe UID·COM·진행 중 세션 | 현재 PC에서 새로 식별. 원시 UID·인증 정보는 공개 문서에 기록하지 않음 |
| 기존 공개 package·release asset | 불변 보존. 문서 정비를 이유로 재생성·덮어쓰기하지 않음 |

## 새 실물 시험을 요청받았을 때만

문서·Host 검토에는 보드를 연결할 필요가 없습니다. 완료한 S/U 시험과 C05 1시간 soak는 재예약하지 않습니다.
새 실기가 필요한 경우 아래 준비를 따릅니다.

- 현재 USB/probe·exact UID hash·role·image를 대조합니다. COM 번호와 USB 순서를 이전 PC에서 가져오지 않습니다.
  USB 열거·SWD 응답·firmware READY는 서로 별개입니다.
- 실제 결선은 [커넥터 핀맵](<01_아두이노 코어 설계/13_NU54DK_P2_P4_커넥터_핀맵.md>)과
  [해당 fixture 계약](../tests/hil/nu54dk/README.md)을 확인합니다. S는 17신호, U는 UART00 4신호로 서로 다릅니다.
- 보드 간 시험은 공통 GND·동일 I/O 전압·전원 레일 미연결·출력 충돌 방지 조건을 지킵니다.
  DAP UART·SWD 스위치와 추가 pull-up 조건은 fixture별 안내를 따릅니다.
- 사용자 확인을 받은 유지 결선에 임의 시간 만료를 적용하지 않습니다. 새 결선·USB/전원 변화나 오류는 실제로
  대조하고, 오류가 나면 GPIO 연결성 확인 후 CMSIS-DAP 레지스터로 원인을 분석합니다.
- 일반 S/U는 SWD 10 MHz·exact UID·배타 lock·sector flash·`auto_unlock=false`·controlled start를 사용합니다.
  자동 mass erase/recover·임의 보드 전환은 하지 않습니다.
- Firmware watchdog·명령 lease를 유지하고 양쪽 STOP·clock 해제·핀 반환을 확인합니다.
  상세 정책은 [작업 지침](../AGENTS.md)을 따릅니다.

## 최종 지원 범위

v0.4.0은 `standard`·`ble`·`fabric` profile, library 9개·예제 30개를 제공합니다.
QDEC20/21은 기본 정·역회전과 SAMPLE/REPORT event 경로를 공개 지원하며,
반복 manual `read()/clear`의 무손실 누산은 보증하지 않습니다.
반복 Serial personality handover·모든 주변장치 동시 조합·정밀 ADC/jitter/음질/신호 무결성도
보증 범위 밖입니다. 과거 FAIL·미실행을 공개 지원 결정만으로 PASS로 바꾸지 않습니다.
