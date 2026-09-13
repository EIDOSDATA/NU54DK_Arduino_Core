# 개발 인계 — M29 W07-C 완료

현재 설치·지원 버전은 **v0.4.1 하나**입니다. 개발 브랜치 `main`은 v0.5.0을 목표로 하며,
M28은 완료했고 M29는 **6/8(75%)**, 시험 ID는 **8/10 PASS**입니다.
이 문서는 재개 지점과 증거를 찾는 안내이며, 최신 사용자 요청이 과거 실행 순서보다 우선합니다.

## 현재 체크포인트

| 구분 | 확인된 상태 |
| --- | --- |
| 공개 배포 | v0.4.1 단독 지원. v0.4.0 T01~T25·R00~R14와 v0.4.1 설치기 유지보수 완료 |
| M28 | W01~W08 **8/8 완료**, capability 6/6·두/세 보드 시험 ID 9/9 PASS |
| M29 | **M29-W01~W06 완료**, W07 진행 중, W08 미착수 |
| W07-C | 두 보드 `M29-SIGN-01`·`M29-EATT-01` PASS |
| 다음 개발 단계 | W07-D 세 보드 `M29-MULTI-01`, W07-E `M29-REG-01`; 둘 다 **NOT RUN** |
| 현재 작업 경계 | 사용자 요청으로 W07-C 뒤 실기 중단. 문서 전수 정비·로컬 검증 완료, CI 결과 확인은 뒤로 미룸 |
| 마지막 실기 source | `c71ef4a21465923760933f6b87ad7d92d9a95698` |
| 실기 결과 반영 commit | `fcfd3e2c22a90c1e842126c512362c0840a5fa45` — 이후 문서 commit과 구분 |
| 소스 버전 문자열 | `0.4.1-dev`. 설치 배포 버전이나 현재 HEAD 대신 사용하지 않음 |

현재 HEAD·실행 중 프로세스·CI 결과·보드 연결은 재개 시 새로 확인합니다.
W07-C 완료가 W07 전체 완료 또는 v0.5.0 릴리스를 뜻하지 않습니다.

## 먼저 읽을 문서

| 목적 | 단일 원본·진입점 |
| --- | --- |
| 작업·보존·실기 원칙 | [AGENTS.md](../AGENTS.md) |
| 현재 제품과 지원 기능 | [프로젝트 README](../README.md), [v0.4.1 TODO](TODO_v0.4.1.md) |
| 현행 진행 상태·후속 순서 | [v0.5.0 개발 계획](TODO_v0.5.0.md) |
| M29 API·고정 자원·시험 계약 | [M29 착수 계약](<01_아두이노 코어 설계/16_M29_ATT_GATT_L2CAP_착수_계약.md>), [`m29-ble-readiness.json`](../variants/nu54dk/m29-ble-readiness.json) |
| M29 W07-C 실제 결과·실패와 수정 이력 | [147번 기록](<04_검증 기록/147_M29_W07_Signed_Write_EATT_HIL_준비.md>) |
| M28 완료 범위·실제 증거 | [140번 기록](<04_검증 기록/140_M28_W07_3보드_HIL과_W08_완료.md>), [`m28-ble-readiness.json`](../variants/nu54dk/m28-ble-readiness.json) |
| v0.4.0 완료·제외·QDEC 지원 계약 | [완료 TODO](TODO_v0.4.0.md), [124번 지원 판정](<04_검증 기록/124_T22전_QDEC_지원_범위_재확정.md>) |
| 전체 탐색·문서 정비 이력 | [문서 목차](README.md), [148번 전수 검토](<04_검증 기록/148_개발문서_전수검토와_README_개선.md>) |

과거 기록의 “다음 실행”, `running`, PC 절대 경로는 당시 상태입니다. 과거 명령을 그대로
재실행하거나, 제거된 build 디렉터리가 현재도 있다고 가정하지 않습니다.

## W07-C에서 확인한 것

Clean exact source `c71ef4a2…`의 두 role target build는 **2/2 PASS, warning 0**입니다.
같은 image를 사용한 한 번의 전체 두 보드 runner에서 다음을 확인했습니다.

| 시험 | 실제 결과 |
| --- | --- |
| Signed Write | 20/20, warm reboot 간 counter rollback 0, replay 수락 0 |
| Sign counter | 반복 뒤 20, replay 검사용 새 원본을 포함한 최종값 21 |
| EATT | 암호화 전 거부·상한 초과 거부, bearer 2개 × 1,000 SDU, production enhanced read/write |
| 오류·재시도 | payload 오류·deadlock·starvation 0, 연결 재시도 0 |
| 증거 | [result.json](<04_검증 기록/evidence/m29-w07-c71ef4a2-signed-eatt/result.json>)과 같은 폴더의 양쪽 raw transcript |

Signed Write는 기본 OFF의 **deprecated legacy opt-in**, EATT는 기본 OFF의
**experimental opt-in**입니다. SDK의 정적 candidate 표시와 실제 구현·실기 PASS는 별개로 유지합니다.
광고 길이, target 상태기계, 정상 disconnect, UART reboot 경계, HCI `0x3e`와
EATT `0x08`의 실패·진단·동일 조건 재검증은 147번에 보존합니다.
인계 문서에서는 이미 해결된 시도별 로그를 반복하지 않습니다.

## 개발 재개 순서

1. 최신 사용자 요청과 위 체크포인트를 확인합니다. W07-C 뒤 중단 요청을 임의로 해제하지 않습니다.
2. 저장소 `main`·HEAD·미커밋 변경·submodule을 확인하고 기존 변경을 보존합니다.
3. M29 계약의 W07-D/E 종료 조건, 구현된 runner와 누락 항목을 먼저 대조합니다.
   두 보드 SIGN/EATT 결과를 세 보드 MULTI/REG의 PASS로 복사하지 않습니다.
4. 실기 재개가 요청되면 세 보드의 역할·현재 USB/DAP/UART·image를 식별하고 해당 시험 조건을 고정합니다.
5. W07 잔여 통과 후 W08의 회귀·예제·지원표·문서·CI를 마감하고 M30으로 인계합니다.

NU54DK 3개와 독립 DAP/UART 3경로는 이전 실기에서 확인했습니다. 현재 연결 상태는 새로 확인해야 합니다.
외부 sniffer와 Android/iOS/Windows/Linux cross-vendor 상호운용, Bluetooth qualification은
현재 PASS 범위에 포함되지 않습니다.

## 저장소와 도구 준비

원격은 `https://github.com/EIDOSDATA/NU54DK_Arduino_Core.git`, 기본 개발 브랜치는 `main`입니다.
새 PC에서는 다음처럼 submodule까지 복제한 뒤
[Windows 개발환경](<02_빌드 설계/09_Windows_개발환경_설정.md>)에 따라 없는 도구만 준비합니다.

```powershell
git clone --recurse-submodules https://github.com/EIDOSDATA/NU54DK_Arduino_Core.git
cd NU54DK_Arduino_Core
git status --short
git submodule status
```

| 고정 입력 | 기준 |
| --- | --- |
| NCS | v3.4.0 / `99553055607b2e9885fbc80ccd11fa9da81c2df0` |
| Zephyr | `bf801e4e3d19e1ffa76164346480cb7734dd2800` |
| Board revision | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| Windows Toolchain bundle | `dcbdc366a1` |

원본은 [CI lock](../tools/ci/ncs-3.4.0.lock.json)과
[prerequisite pins](../tools/nu54-prerequisites/pins.json)입니다.
Host compiler/linker와 target PATH를 분리하고 고정 NCS CMake/Ninja를 사용합니다.
SDK 설치 상태 파일이나 이전 PC의 절대 경로 cache를 복사해 검증 완료로 간주하지 않습니다.

문서 변경은 `python -B tools/ci/run_m12_gate.py docs`와 관련 contract/readiness 검사로 확인합니다.
코드 변경은 영향에 따라 Host·target·실기를 추가합니다. 이전 source의 PASS와 새 실행을 구분하고,
CI 확인을 미룬 경우 대상 commit과 미확인 상태를 남깁니다.

## 보존 자료와 임시 경로

| 자료 | 취급 방법 |
| --- | --- |
| 코드·문서·정규화 로그·raw 압축·SHA manifest | Git과 검증 기록의 evidence에서 보존 |
| 이력 정리 전 source·공급 종료 자산 | [106번 archive 안내](<04_검증 기록/106_Git_이력_정리와_구버전_패키지_공급_종료.md>)를 따름 |
| ELF/HEX·compile DB·build cache | 필요할 때 exact source와 고정 SDK로 재생성. 이전 로컬 경로를 재사용 가능하다고 가정하지 않음 |
| SDK·툴체인·저장소 | 임시 출력과 구분. 디렉터리 이름만 보고 삭제하지 않음 |
| Probe UID·COM·세션 | 현재 PC에서 새로 식별. 원시 UID·인증 정보는 공개 문서에 추가하지 않음 |
| 기존 공개 package·release asset | 불변 보존. 문서 정리로 덮어쓰지 않음 |

짧은 build 경로가 필요하면 사용 중이지 않은 경로를 확인하고 생성한 출력·매핑을 기록합니다.
`SUBST`로 임시 drive를 만들었다면 작업 종료 때 그 매핑을 해제합니다.
과거에 사용한 C:/D: 임시 출력과 H: 매핑은 영구 build 입력이 아닙니다.

## 실물 시험·지원 경계

실기 안내는 [HIL README](../tests/hil/nu54dk/README.md), 결선은
[P2/P4 핀맵](<01_아두이노 코어 설계/13_NU54DK_P2_P4_커넥터_핀맵.md>)과 해당 fixture 계약을 따릅니다.
오류가 나면 GPIO 연결성을 먼저 확인하고 CMSIS-DAP으로 주변장치·DMA·GPIO·IRQ·오류 레지스터를
확보해 원인 분류 → 수정 → 동일 조건 재검증을 진행합니다. 이유 없는 무한 재시도는 하지 않습니다.
Exact UID/image·배타 probe lock·sector flash·`auto_unlock=false`, watchdog/lease와 STOP·핀 반환을 유지합니다.

v0.4.1의 QDEC20/21은 기본 정·역회전·SAMPLE/REPORT event 경로를 지원합니다.
반복 manual `read()/clear` 무손실 누산, 반복 Serial personality handover, 모든 주변장치 동시 조합,
정밀 ADC 정확도·jitter·음질·신호 무결성은 보증하지 않습니다.
완료된 T13 S/U와 C05 1시간 soak를 문서 정비 때문에 다시 예약하지 않습니다.
