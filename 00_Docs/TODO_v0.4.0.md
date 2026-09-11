# v0.4.0 개발 현황과 실행 TODO

현재 정식 배포는 **v0.3.0**입니다. v0.4.0은 합의한 T13 S/U, T14 충돌 판정,
T15 지원 범위, T16 설치 통합, T17 문서 정리, T18 공개 절차 준비, R14/T19 RC 고정,
T20 설치 수명주기와 T21 stable 최종 검사를 완료했습니다. 2026-09-11 프로젝트
소유자가 QDEC20/21을 제한이 명시된 공개 지원으로 전환하기로 결정했고, 변경된 후보의
T19~T21 영향 gate도 다시 통과했습니다. 현재는 최종 문서 커밋의 stable plan에 T22 승인을
결합한 뒤 T23~T25 공개·공개 URL 검증·마무리를 진행하는 단계입니다.
현재 상태와 다음 작업은 이 문서에서 관리하고, 실행별 원본은 [검증 기록](<04_검증 기록/README.md>)에 보존합니다.

## 1. 현재 상태

| 마일스톤 | 상태 | 근거와 남은 일 |
| --- | --- | --- |
| T01~T09 준비, R00~R13 리팩토링 | 완료 | 준비·Host·target: 43~66번 |
| T11 통신 단독 기능 회귀 | 완료 | source별 UART/SPI/TWI 일곱 묶음: 67~73번 |
| T12 GPIO·Analog·Timer·Stream 기능 | 사용자 수용 완료 | 합의한 기능 범위 완료, source별 원본은 74~103번에 보존 |
| T13 정상 안정성 | 완료 | 단독 29/29 + 동시 7/7 = 36/36, 대표 C05 3600초 포함. 각 시험 당시 source의 결과 |
| T13 고정 serial 취소/NACK | 완료 | 21/21 |
| T13 PWM 복구 | 완료 | 6/6 |
| T13 serial 자원 충돌 | 사용자 수용 완료 | 예행 14/14, 5조건 각 100회. 나머지 9조건 반복 생략 승인 |
| T13 I2S/PDM 복구 | 4/4 | I2S role2 공급 중단·재시작 정식 100/100 완료. 111번 |
| 요청한 잔여 S 1~3단계 | **범위 종료: PASS 56 + 제외 2 / 58** | System OFF 2조건은 기존 M15 실기와 중복되는 T13 추가 결합 시험으로 제외. 113번 |
| T13 U 준비·실행 | **완료** | `4f380931` exact image에서 UARTE00 180초, RTS/CTS 200/200, TX/RX 취소 400/400 PASS. 115번 |
| T14 결함·충돌 판정 | **완료** | PWM 자원 식별 1건 해결, 세 미커버 요구 판정 완료. 116번 |
| T15 지원 범위 확정 | **완료** | M24/M25 fixture physical gate PASS. 당시 QDEC partial·비공개 판정은 124번에서 제한 명시 공개 지원으로 재확정 중 |
| T16 설치 통합 | **완료** | `fabric` profile·facade·예제·30개 후보 lock. 118번 |
| T17 문서·지원 매트릭스 정리 | **재조정 완료** | public 64/75, QDEC20/21 partial 근거·지원 계약과 사용자 문서 일치. 124번 |
| T18 공개 절차 준비 | **완료** | stable 생성·검증, 승인 evidence 결합과 공개 명령 분리. 120번 |
| R14·T19 RC 고정·전체 회귀 | **재검증 완료** | exact `1e97ae49`, 35/35 target·원격 CI·RC 이중 재현 PASS. 124번 |
| T20 RC 설치 수명주기 | **재검증 완료** | 새 RC 설치·30/30 예제·Upload·전환·제거·재설치 PASS. 124번 |
| T21 stable 최종 검사 | **재검증 완료** | 새 stable 이중 재현·30/30·Upload·RC runtime 동등성 PASS. 123·124번 |
| T22~T25 승인·공개·마무리 | **T22 exact 결합 진행** | 조건부 승인 요건 충족; 최종 plan 결합 뒤 T23~T25 연속 진행 |

T13 QDEC manual read 단독/C07·시리얼 핸드오버·peer 제어 System OFF 제외와 충돌 반복 생략은 범위 결정이며 새 물리
PASS가 아닙니다.
기존 정상 36조건과 수용된 시험을 다시 예약하지 않습니다.

## 2. 현재 재개 체크포인트

**2026-09-11 T22 직전 지원 범위 조정과 영향 재검증 완료:** 프로젝트 소유자는 QDEC20/21을 공개 지원으로
전환하되, 검증된 기본 정·역회전과 SAMPLE/REPORT event 경로를 지원 근거로 사용하고 동작 중
반복 manual `read()/clear`의 무손실 누산은 보증 범위에서 제외하기로 결정했습니다. 반복 Serial
personality handover, 모든 주변장치 동시 조합, 정밀 ADC 정확도·clock jitter·음질·신호 무결성도
기존처럼 보증 범위 밖입니다. 이 작업은 과거 QDEC 실패를 PASS로 소급 변경하지 않으며,
manifest·공개 capability·API 주석·사용자/릴리스 문서·계약 검사를 일치시켰고 변경된 후보로
T19 35/35·CI·RC 재현성, T20 RC 설치 수명주기, T21 stable 재현·30/30·Upload를 다시
통과했습니다. 프로젝트 소유자의 조건부 T22 승인 조건도 충족했습니다. 실행 기록은
[124번](<04_검증 기록/124_T22전_QDEC_지원_범위_재확정.md>)에 남깁니다.

**2026-09-10 기준: 요청한 S 정리와 U 실행 준비를 먼저 완료했습니다.** 이어진 114번 문서 정비에서는
본 저장소 Markdown 228개와 고정 보드 문서 6개를 검토했고, 그 정비 자체에는 보드 접근·GPIO 구동·
flash·U 실기가 없었습니다. 당시 검토 범위와 검사 결과는
[114번](<04_검증 기록/114_전체_문서_정비와_남은_마일스톤.md>)에 기록합니다.

**T13 U 최소 결선·exact image·물리 실기를 완료했습니다.** 완료한 S/U 시험을 다시 시작하지 않습니다.
T21에서 T20 결과를 반영한 RC/stable 이중 재현·runtime 동등성·stable 설치·실제 Upload를
완료했습니다. 현재 단계는 T22에서 exact 결과와 공개 자산을 프로젝트 소유자가 확인하고 명시적으로
승인하는 것입니다.
T13 종료는 [115번](<04_검증 기록/115_T13_U_UART00_완료와_T13_종료.md>)에 기록했으며 정식 공개를 포함하지 않습니다.

2026-09-10 후속 실행 결과: `7f78a36c`에서 U 결선 검사를 net 11·13·15·16으로 한정하고
S의 17신호 검사를 유지했으며 Host 30/30을 통과했습니다. C drive 정리 뒤 clean exact source
`4f380931`에서 두 역할 image를 2/2 재생성하고 U 실기를 완료했습니다. 정상 180초,
RTS/CTS 양 역할 각 100회, TX/RX 취소 양 역할 각 100회가 모두 PASS했습니다.

T14/T17 문제 문서 **29개 정비 완료**: **해결 완료 / 검증·판정 미완료 / 실기 미실행**을 분리했습니다.
해결한 문제는 아래 상태 칸에 명시하고, 제외된 항목은 현행 문제·잔여 표에서 삭제했습니다.
Markdown 229개 UTF-8·로컬 링크와 diff 검사를 통과했으며 비문서 변경은 없었습니다.
원본 이력과 지원 제한은 보존했고 해당 문서 정비는 `4f380931`까지 커밋·푸시했습니다.

2026-09-10 T14 완료: 전체 GPIO alias·DMA overlap과 활성 GPIOTE·DPPI 충돌을 production
자원 관리자 회귀로 판정했습니다. Fabric PWM의 자원 식별 불일치 1건을 발견해 `24582dcc`에서
교정했고, Host·target build와 두 nRF54L15 보드의 28 command·520 cycle HIL을 통과했습니다.
세부 근거는 [116번](<04_검증 기록/116_T14_자원_충돌_판정과_PWM_식별_교정.md>)을 따릅니다.

2026-09-10 T15 완료: 75개 manifest의 HIL·동시 HIL 상태를 원본 결과에 맞춰 교정했습니다.
M24는 23 identity 기능 HIL pass, M25는 34 pass·QDEC20/21 partial이며,
`m24_fixture_hil`과 `m25_fixture_hil`을 PASS로 확정했습니다. release blocker는 8개에서 6개로
줄었고, frozen RC·설치·공개 gate는 그대로 남습니다. 세부 근거는
[117번](<04_검증 기록/117_T15_지원_범위와_Physical_Gate_확정.md>)을 따릅니다.

2026-09-10 T16 완료: `14a979620bb2`에서 별도 `fabric` profile, 설치 library facade와
`FabricCapabilities` 예제를 연결했습니다. 실제 격리 Arduino 설치 경로에서 수동 Kconfig 편집 없이
빌드했고 target 324/324, 영향 Host 24 PASS·조건부 1 SKIP, CI 46/46을 통과했습니다. 당시 QDEC는
`unsupported`였고, v0.3.0 stable 예제는 29개로 유지합니다. 세부 근거는
[118번](<04_검증 기록/118_T16_Peripheral_Fabric_설치_통합.md>)을 따릅니다.

2026-09-10 T17 완료: T16에서 설치 경로에 연결한 지원 범위를 manifest·계약·생성 문서·사용자
문서에 일치시켰습니다. 당시 75개 identity 중 62개는 `public`과 HIL `pass`, QDEC20/21은
`internal`·`partial`과 profile `unsupported`로 유지했습니다. 이 검증 기록을 포함한 Markdown 239개 UTF-8·로컬 링크,
Host·CI·inventory·generated·style 검사를 통과했고, release notes·migration·known issues·testing·
troubleshooting 문서를 추가했습니다. 과거 검증 기록은 당시 조건의 증거이므로 삭제하지 않았습니다.
세부 근거는 [119번](<04_검증 기록/119_T17_문서와_지원_매트릭스_정리.md>)을 따릅니다.

2026-09-10 후속 사용자 결정: GPIO 전달·SWD 진단은 현재 문제 목록에서 제거합니다.
SPI CS 조기 종료의 별도 slave 판정은 추가 검증에서 제외하고, TWIS는 완료한 2ms 공급 지연
시험으로 수용하여 별도 read-request 지연 시험을 요구하지 않습니다. 이 결정은 T14/T17 문서에
반영하며, 기존 원본·실기 PASS 수는 유지하고 세 항목을 남은 작업으로 다시 등록하지 않습니다.

### 완료 수와 잔여 항목

분모 58은 이번 요청의 S 정리 범위이며 v0.4.0 전체 진행률이 아닙니다.
구성은 I2S 1 + S 오류 복구 54 + System OFF 2 + 기존 요구 대조 1입니다.

| 항목 | 완료 / 전체 | 상태 |
| --- | ---: | --- |
| UART break | 8 / 8 | 양 역할, 각 100회 |
| UART parity | 8 / 8 | 양 역할, 각 100회 |
| UART CTS | 12 / 12 | 단독 및 C01/C05 조건 완료 |
| UART RX 공급 지연 | 8 / 8 | 양 역할 400/400씩, 합계 800회 |
| 기존 요구·구현·증거 대조 | 1 / 1 | 대조 완료, 미실기를 PASS로 대체하지 않음 |
| I2S 원래 경로 복구 | 1 / 1 | role2 starvation/restart 정식 100/100 완료 |
| SPI 경계 복구 | 10 / 10 | short·unready, 5개 인스턴스 각 100회 |
| TWI SDA stuck-low | 4 / 4 | TWIM20/21/22/30 각 100회 |
| TWIS 공급 지연 | 4 / 4 | TWIS20/21/22/30 각 100회 |
| **합계** | **PASS 56 + 제외 2 / 58** | **요청한 S 범위 종료, 미실행을 PASS로 계산하지 않음** |

### 해결 완료한 문제

| 문제 | 현재 상태 | 해결 내용·검증 근거 |
| --- | --- | --- |
| 초기 UART deferred RX·SPI RXDELAY·TWIS 지연 버퍼 재개 | **해결 완료** | 각각 수정 후 전체 재시험 PASS. 44·47·50번 |
| UART 오류 callback 폭주·진행 중 RX abort 중복 STOP | **해결 완료** | core와 시험 시작 순서 교정, break/parity 16조건 각 100회. 110번 |
| C01 UART/TWI 버퍼 재공급 누락 | **해결 완료** | UARTE 반환 버퍼 재공급·TWIS 승격 버퍼 prepare 교정, C01 900초와 양 역할 CTS 100회. 110번 |
| UART RX 지연 시험의 재시작 slot 오류 | **해결 완료** | `completed % 2`로 시작 slot 선택, `3f4a1890` 양 역할 각 400회·cleanup 통과. 110번 |
| I2S 짧은 버퍼의 DMA 자원 처리 지연 | **해결 완료** | `36ba819` 수정 후 Fixture 430 전체 192조건 PASS. 87번 |
| I2S S 수신·재시작 오류 | **해결 완료 — 결선 문제** | 사용자 원인 확인. 원래 role2 정식 100/100·cleanup 203·idle 400 통과. 111번 |
| SPI SPIS 연속 버퍼 공백·재시작 zero RX | **해결 완료** | 선행 버퍼 예약·시작 장벽·CS inactive·지연 교정, short/unready 10조건 각 100회. 111~112번 |
| TWI 반환 terminal 버퍼 재공급 | **해결 완료** | stuck-low 4조건 각 100회와 정상 통신 복구. 112번 |
| TWIS 공급 지연 측정 기준 | **해결 완료** | 2ms 공급 지연 4조건 각 100회와 복구 확인, 사용자 수용 완료. 112번 |
| PDM 스테레오 위상·모노 gate 준비 순서 | **해결 완료** | 합성 신호·준비 순서 교정, 기본 192·밀도 32·연속 96/96 통과. 91~92번 |
| PWM 미시작 `start_via_task` STOP timeout | **해결 완료** | `080d771` core 수정·두 보드 회귀, 후속 S PWM 복구 6/6 완료. 94·109번 |
| Fabric PWM과 public PWM의 block 자원 식별 불일치 | **해결 완료** | `24582dcc`에서 공통 `pwm_block + instance` 키로 교정. Host 회귀·target 4/4 build·두 보드 520 cycle HIL. 116번 |

공개 System OFF timer·사용자 버튼 wake는 **검증 완료(정상)**입니다. M15에서 GRTC cause 2048과
SW0/P1.13 cause 128을 실제 확인했으며 이후 공개 API의 실질 변경은 없습니다. 수정 대기 결함이 아닙니다.

### T14 검증·판정 결과

현재 작업 범위에서 수정 대기 중인 확정 코어 결함은 없습니다.

| 항목 | 현재 상태 | 판정 근거 |
| --- | --- | --- |
| 전체 GPIO alias·DMA overlap 충돌 | **검증·판정 완료** | production 자원 관리자에서 alias·overlap 중복 거부와 기존 소유자 snapshot 보존. M14의 31 pad mapping 전수 계약과 결합 |
| GPIOTE·DPPI active 충돌 | **검증·판정 완료** | 활성 DPPI20 중복 lease·publisher 거부와 enable·endpoint 보존. 실제 DPPI10/20 두 보드 반복·반환 |
| Fabric PWM과 analogWrite/tone/Servo 충돌 | **결함 해결·판정 완료** | PWM block 공통 키 교정. 현재 Kconfig는 Fabric과 public ADC/PWM을 상호 배타적으로 구성하므로 동시 물리 API는 지원 구성이 아님 |

원인 분석·수정 source·캠페인과 원본 위치는
[110번](<04_검증 기록/110_문서_정리와_T13_S_잔여_재개.md>)과
[111번](<04_검증 기록/111_T13_S_I2S_완료와_SPIS_연속_버퍼_교정.md>)을 따릅니다.
[112번](<04_검증 기록/112_T13_S_SPI_TWI_완료와_System_OFF_원인.md>)에 SPI/TWI/TWIS 완료와
System OFF 레지스터·공식 예제 기준선을 정리했습니다.
[113번](<04_검증 기록/113_T13_S_범위_종료와_U_준비.md>)은 마지막 재실행·GPIO 진단, 기존 M15와의
중복 판정, S 범위 종료와 U 준비 기준을 기록합니다.
[115번](<04_검증 기록/115_T13_U_UART00_완료와_T13_종료.md>)은 U 실기와 T13 종료를 기록합니다.
디버거 관측, 변경된 경로의 성공, 예행과 부분 반복은 정식 완료 수에 더하지 않습니다.

### 실행 source와 준비 상태

| 용도 | source / build | 확인된 범위 |
| --- | --- | --- |
| UART RX 지연 완료 image | `3f4a18906f6d72df45f5a07f901b6a7aef716a2a` / `C:/t5t04` | 해당 시험의 기준선이며 마지막 보드 image가 아님 |
| 마지막 T13 System OFF 시도 | `dee41fe62eea96f718bcb46e96c1312c7507d5be` / `C:/tz19` | T13 결합 PASS 없음, 원본 보존 뒤 범위 제외 |
| S 정식 완료 image | `914ccd16`·`1c02f9de`·`d39f0742`·`e8e776e9` | SPI short/unready 10, TWI 4, TWIS 4 각 100회 |
| U 완료 image | `4f38093181d9ecc51076acb5a29c2fd3b900107a` / `C:/u13c` | U 전용 DUT/peer 2/2, 4-net 결선·180초·flow 200회·취소 400회 PASS |
| 공개 System OFF 기능 근거 | `c47239d954c45fd173d8d1393e3ea5c9c86e111a` | M15 timed/button 실기 PASS; 후속 API 실질 변경 없음 |

113번 작성 당시 종료 관측은 두 보드 P1.04 `PIN_CNF=0`과 CPU 실행·sleep 복구입니다.
이후 U 실행의 별도 SWD·결선·최종 핀 상태는 115번 원본으로 구분합니다.

U 완료는 UART00 180초 full-duplex, 양 역할 RTS/CTS와 TX/RX 취소 시험을 exact image와 별도
U 결선 검사로 실제 통과했다는 뜻입니다. S 확인을 U 재결선 확인으로 재사용하지 않았습니다.
상세 원본·hash·초기 CMSIS-DAP 타임아웃 진단은 115번을 따릅니다.

### 결선 확인과 실패 처리

- 현재 물리 결선은 UARTE00의 TX↔RX·RTS↔CTS 4신호 + 공통 GND입니다. 정확한 A↔B 표와
  전기 조건은 [T13 계획](../tests/hil/nu54dk/T13_PLAN.md)을 따릅니다. 연결하지 않은 나머지
  13신호를 U 검사 대상으로 요구하지 않습니다.
- 사용자는 결선을 유지하며 손대지 않는다고 확인했고, 시간 경과에 따른 유지 확인 만료를 폐기했습니다.
  **12시간·30분 같은 임의 기한만으로 중단하거나 재확인을 요구하지 않습니다.**
- 새 물리 캠페인을 시작할 때 해당 배치의 전체 GPIO 연결성을 먼저 검사합니다. 이상이 생기면 먼저 연결성을 다시 확인하고,
  nRF54L15의 CMSIS-DAP 디버거로 GPIO·주변장치·DMA·IRQ·버퍼 상태를 보존해 원인을 진단합니다.
- 실패 원인 규명 → 원인에 근거한 수정 → 동일 조건 재검증 순서를 지킵니다. 이유 없는 동일 실행의
  무한 반복이나 독립 시험으로 진행률만 올리는 실행은 하지 않습니다.
- T13 S/U runner는 유지 결선 확인의 임의 시한을 제거했습니다. firmware 명령 lease·watchdog,
  exact UID/image·단절 fault latch는 유지하며 새 사용자 확인을 임의로 만들어 우회하지 않습니다.
- firmware watchdog·명령 lease·STOP·출력 충돌 방지·배타 probe lock은 계속 유지합니다.
  이는 사용자의 결선 유지 확인에 임의 만료 시간을 붙이는 정책과 다릅니다.
- 실제 결선 변경, USB/전원 변화, STOP 실패 등 새 이상은 확인·진단 대상으로 기록합니다.
  물리 재결선이 꼭 필요하면 정확한 선과 필요한 조치를 안내합니다.
- 양쪽 STOP·clock 해제·GPIO 반환을 확인한 뒤 다음 시험을 시작합니다.
  일반 S/U 경로는 SWD 10 MHz·exact UID·sector flash·`auto_unlock=false`를 유지하며
  mass erase/unlock/recover는 금지합니다. 제외한 System OFF 전용 접속 절차를 다시 수행하지 않습니다.
- T13 S/U의 합의 범위는 종료했습니다. QDEC 재진단·시리얼 핸드오버·T13 peer 제어
  System OFF 추가 결합 시험은 제외 상태를 유지합니다. T13을 이유로 이 항목을 다시 예약하지 않습니다.

### 구현·문서·Git 규칙

1. 실제 저장소·branch·HEAD·dirty·board gitlink를 확인하고 기존 변경을 보존합니다.
2. source·image·역할·HEX hash·실행기·Host/target 결과를 결합합니다. 문서 커밋을 이전 image의 source로 바꾸지 않습니다.
3. 한국어 Doxygen, BSD/Allman·4칸, 제어문 중괄호를 지킵니다. SDK·third-party·board 원본은 임의 수정하지 않습니다.
4. 필요한 Host·target·계약·문서·정렬 검사를 수행합니다. 구현·build·진단·실기 결과는 구분합니다.
5. 커밋·푸시를 수행한 경우 해당 exact SHA의 CI를 확인합니다. 진행 중 CI를 성공으로 기록하지 않습니다.
6. 매 보고에 완료 범위와 진행률을 함께 적습니다. 문서 정리 진도와 S 실기 58조건의 진행률은 구분합니다.
7. 종료·인계 시 현재 체크포인트와 해당 검증 기록을 갱신합니다. 최신 사용자 지시는 과거 일지보다 우선합니다.

## 3. 작업별 원본과 범위

| 작업 | 먼저 대조할 원본 |
| --- | --- |
| 전체 범위·상태 | [로드맵 §8](<./01_아두이노 코어 설계/02_구현_로드맵.md>), [경쟁 마일스톤 M24~M27](<./01_아두이노 코어 설계/08_전_인스턴스_DMA_BLE_경쟁_마일스톤.md>), [42번 합의](<./04_검증 기록/42_v0.4.0_코어_기능_검증_범위_합의.md>) |
| 리팩토링 안정화·선행 구조 작업 | [리팩토링 문서 안내](<./01_아두이노 코어 설계/14_리팩토링/README.md>), [통합 실행계획](<./01_아두이노 코어 설계/14_리팩토링/02_리팩토링_통합_실행계획.md>), [진행 체크리스트](<./01_아두이노 코어 설계/14_리팩토링/05_리팩토링_진행_체크리스트.md>) |
| 인스턴스·공유 자원·DMA | [inventory JSON](../variants/nu54dk/peripheral-manifest.json), [생성 matrix](<./01_아두이노 코어 설계/09_M23_Peripheral_인스턴스_매트릭스.md>), [serial 계약 JSON](../variants/nu54dk/serial-fabric-contract.json) |
| 통신·analog·stream 후보 | [SerialFabric](../cores/arduino/nucode/SerialFabric.h), [AnalogFabric](../cores/arduino/nucode/AnalogFabric.h), [StreamFabric](../cores/arduino/nucode/StreamFabric.h), [Kconfig](../zephyr/Kconfig), [M24 계약](<./01_아두이노 코어 설계/10_M24_Serial_Fabric_경로와_API_계약.md>) |
| HIL·결선·환경 | [HIL README](../tests/hil/nu54dk/README.md), [Windows 개발환경](<./02_빌드 설계/09_Windows_개발환경_설정.md>), [보드 회로도](<../board_package/NU54DK_Zephyr_DTS/NU54-DK Schematic.pdf>)와 해당 board source |
| M25·M26 구현 이력 | [37번 M25](<./04_검증 기록/37_M25_Analog_Event_Stream_Fabric과_온보드_HIL_준비.md>), [M26 지원 경계](<./01_아두이노 코어 설계/11_M26_System_Peripheral_지원_경계.md>), 41번의 최신 기본 실기 증거 |
| RC·공개 | [M27 도구 안내](../tools/release/M27_README.md), [RC 준비 문서](<./05_릴리스/v0.4.0-rc.1/README.md>), [readiness](../variants/nu54dk/v0.4.0-release-readiness.json) |

범위는 Windows용 `v0.4.0` 코어 기능이다. Linux/macOS 지원과 새 BLE 확장을 추가하지 않는다.
온보드 자원·두 NU54DK의 안전한 peer/loopback·합성 신호·capture를 사용하며, 필요한 점퍼·풀업은
시험별로 안내한다. 외부 마이크/코덱/엔코더별 호환성, 정밀 ADC·jitter·전력·음질·신호 품질은
필수 gate 밖이다. **코어의 실제 데이터 경로·DMA·오류 복구·동시성·soak는 면제하지 않는다.**
합성 peer로도 신호를 생성·검증할 수 없는 필수 경로는 HOLD이며, 추가 범위 변경은 사용자에게 확인한다.

생성 문서는 JSON·생성기를 고친 뒤 재생성한다. Board submodule, SDK와 기존 공개 자산은 임의로
수정하지 않는다. `v0.3.0` 미만 공개 공급은 종료했다. 이전 tag·asset 원본은106번의 archive에 보존하며 현재 공개 자산은 변경하지 않는다.

## 4. A단계 — 결선 없이 준비 (T01~T09, 완료)

T01~T08의 상세 초기 계획·구현 대조·실패/수정 이력은
[43번 준비 기록](<04_검증 기록/43_v0.4.0_시험_준비와_구현_대조.md>)에 보존합니다.
완료한 준비 작업을 현재 대기 목록으로 다시 등록하지 않습니다.

- [x] **T01 — 최종 시험 목록 확정:** 75개 identity·19개 family, test ID·route·속도·buffer·반복·판정 기준 고정.
- [x] **T02 — 코드와 검증 상태 대조:** source·build·실기·공개 API·profile을 분리하고 보완 항목 연결.
- [x] **T03 — 두 보드 공통 실행기:** exact UID·role·image·nonce·배타 lock·실패 journal·STOP 계약 준비.
- [x] **T04 — UART·SPI·I2C 시험 프로그램:** 각 인스턴스의 송수신·mode·DMA·flow/error·취소·재시작 판정 준비.
- [x] **T05 — ADC·PWM·타이머·이벤트 시험:** 안전한 입력·capture·sample/count·소유권 판정 준비.
- [x] **T06 — PDM·I2S·QDEC 합성 신호:** 신호원과 수신 oracle 준비. 당시 준비 완료와 후속 실기 결과는 별개.
- [x] **T07 — DMA·복구·동시성·안정성 실행기:** 오류 주입·buffer 반환·누수·유한 반복·soak 기준 준비.
- [x] **T08 — 결선표와 스위치 안내:** fixture별 GPIO·GND·전압·pull-up·DAP UART 분리·금지 net 계약 확정.
- [x] **T09 — Host·target·무배선 회귀:** 준비 source와 실제 image를 대조하고 온보드 시험 완료.

T09 주요 근거:

| 실행 시점 | 검증 범위 | 기록 |
| --- | --- | --- |
| 준비 종료 `696defb` | 두 역할 target 2/2, 무배선 primitives 904 PASS | [43번](<04_검증 기록/43_v0.4.0_시험_준비와_구현_대조.md>), [원본](<04_검증 기록/evidence/696defb/pair-primitives-696defb.json>) |
| DAP UART 회귀 `373d98d`·BLE `18a7cbe` | 온보드 18 PASS, M19/M20/M21 pair PASS | [66번](<04_검증 기록/66_T09_UART_유휴_bias와_BLE_회귀.md>) |
| R13 이후 `c94298f` | 두 보드 온보드 904 PASS | [65번](<04_검증 기록/65_R13_후속_USB_무배선_실기와_정리.md>) |

당시 외부 fixture가 NOT RUN이었다는 사실은 유지합니다. 후속 T11/T12 완료를 취소하거나
T09 온보드 PASS로 외부 실기를 대신하지 않습니다.

## 5. B단계 — 결선·기능·복구 검증 (T10~T15)

- [x] **T10 — 첫 시험 묶음의 결선 확인:** Fixture 101의 보드·DAP UART 분리·USB 재연결을 확인했습니다.
  근거는 [44번](<04_검증 기록/44_M24_Fixture_101_UART_실기_검증.md>)입니다.
  실제 결선을 바꾸면 새 표를 확인하지만 유지 중인 S에 임의 만료 시간을 적용하지 않습니다.

- [x] **T11 — M24 통신 인스턴스 기능 검증:** UART 101~103, SPI 201~203, TWI 301을 완료했습니다.
  초기 결과는 44~50번, R00~R13 후 current-source 회귀 7묶음·61,423개 기능은
  [67~73번 기록](<04_검증 기록/README.md>)에 있습니다. 각 source의 단독 PASS를 후속 source·동시성 PASS로 복사하지 않습니다.

### 리팩토링과 최종 회귀의 연결

- [x] **R00~R13:** 정확성 안정화·구조 리팩토링과 software gate 완료.
  단계별 기준·완료 근거는 [리팩토링 체크리스트](<01_아두이노 코어 설계/14_리팩토링/05_리팩토링_진행_체크리스트.md>)에서 관리합니다.
- [x] **current-source T11:** R13 이후 영향 통신의 단독 회귀 완료. 후속 runtime 변경은 영향받는 동일 조건을 재검증합니다.
- [x] **R14:** T16~T18 사용자 통합 뒤 T11~T15 결과를 포함해 RC를 다시 고정하고 T19로 전환했습니다. [121번 기록](<./04_검증 기록/121_T19_RC_소스_고정과_전체_회귀.md>)을 따릅니다.

- [x] **T12 — M25 입력·출력·스트림 기능 검증:** 합의한 범위를 사용자가 완료로 수용했습니다.
  미실행 반복과 실패 원본을 유지하며, 제외된 조건을 PASS나 결함 해결로 바꾸지 않습니다.

| T12 범위 | 완료·제한 근거 |
| --- | --- |
| ADC/PWM fixture 401~408 | 74~79·82~83번. 401~404/408 각 48조건, 공유 AIN4/5/6 각 12조건 |
| I2S fixture 430 | 87번 192조건 PASS |
| PDM fixture 440 | 91~92번 기본·밀도·연속 96/96, 초기 실패와 후속 수정 구분 |
| 내부 ADC·TIMER·이벤트 | 95번. TIMER 7,040회 범위와 완료 결정은 103번 |
| C 공통 GPIO/PWM/I2S | 100번. GPIO/GPIOTE 2,502, PWM 675+288, I2S 432 PASS |
| 반복 수·실행 범위 차이 | 103번. 계획 수치를 실제 실행 수로 대체하지 않음 |

각 기록은 [검증 목차](<04_검증 기록/README.md>)에서 찾습니다. 제외된 항목의 원본과 제한은
기존 이력에 보존하며 현재 수정·재시험 목록에는 넣지 않습니다.

- [x] **T13 — 복구·동시 실행·장시간 안정성 검증**
  - 현행 시간 기준: 사용자 지시로 단독 각 인스턴스 180초. 동시 각 확정 조합 900초, 전체 대표 고부하 한 조합 3600초로 대체. 결과에는 요청/실제 연속 시간을 모두 기록하고 3분을 10분·2시간 통과로 확대하지 않는다.
  - 상태·선행: **합의 범위 완료**. S는 PASS 56 + System OFF 추가 결합 2건 제외, U는 115번의 UART00 물리시험 PASS다. QDEC20/21 manual read 단독·C07 및 연속 handover는 제외하며 T12 완료를 다시 보류하지 않는다.
  - 완료 실행: UARTE00 1 Mbit/s 8N1 full-duplex 180초, 양 역할 RTS/CTS 각 100회, TX/RX DMA 취소·fresh restart 각 역할 100회. 완료한 S 정상 36조건(C05 3600초 포함)과 수용된 충돌·복구를 중복 예약하지 않는다.
  - 완료 기준: source·topology·rate·시간·buffer·loss·latency/CPU 관측 방법과 누수/복구 판정이 기록된다. 장시간 시험을 코드 구현만으로 완료 처리하지 않는다.
  - 결선·증거: [T13 계획](../tests/hil/nu54dk/T13_PLAN.md), 생성 topology JSON과 [115번 완료 기록](<./04_검증 기록/115_T13_U_UART00_완료와_T13_종료.md>)에 원래 계획·적용 범위·원본 hash를 구분한다.

- [x] **T14 — 발견된 결함 수정과 재시험**
  - 완료 결과: GPIO alias·DMA overlap, 활성 GPIOTE·DPPI, Fabric/public PWM 자원 충돌 요구를 모두 판정했습니다.
  - 결함 상태: PWM block 식별 불일치 1건을 발견해 `24582dcc`에서 해결했고 미해결 확정 코어 결함은 0건입니다.
  - 회귀: 계약 46개, 전체 Host, inventory·생성 계약, target 4/4 build, 두 보드 28 command·520 cycle HIL을 통과했습니다.
  - 결선·증거: [116번 기록](<./04_검증 기록/116_T14_자원_충돌_판정과_PWM_식별_교정.md>)과 익명화한 `hardware.json`을 따릅니다.

- [x] **T15 — 실기 결과와 지원 범위 확정**
  - 완료 결과: M24 23 identity HIL pass, M25 34 pass·QDEC20/21 partial을 manifest에 반영했습니다.
  - 지원 경계: T15 당시 public 14개와 설치 통합 전 internal candidate를 분리했습니다. T16~T17에서 지원 판정이 끝난 identity를 `fabric` profile public으로 승격했고 QDEC 제한은 유지합니다.
  - readiness: `m24_fixture_hil`·`m25_fixture_hil` PASS, 전체 release blocker 6개 유지.
  - 결선·증거: 추가 실기 없음. [117번 기록](<./04_검증 기록/117_T15_지원_범위와_Physical_Gate_확정.md>)을 따릅니다.

## 6. C단계 — 사용자용 패키지와 최종 RC (T16~T21)

- [x] **T16 — 검증된 후보 API를 사용자용 설치 경로에 통합**
  - 완료 결과: `fabric` profile·`NUCODE_Peripheral_Fabric.h`·capability·설치 예제와 M27 30개 lock을 연결했습니다.
  - 지원 경계: 기존 singleton과 직접 Fabric은 profile로 분리합니다. QDEC20/21은 124번에서
    SAMPLE/REPORT event 경로 지원과 반복 manual read/clear 무손실 제외 계약으로 재확정합니다.
  - 검증: 실제 격리 설치본과 T16 target build, Host·CI·inventory·style gate를 통과했습니다.
  - 결선·증거: 새 flash·결선 없음. [118번 기록](<./04_검증 기록/118_T16_Peripheral_Fabric_설치_통합.md>)을 따릅니다.

- [x] **T17 — 문서·지원 매트릭스 정리**
  - 완료 결과: README·API·예제·pin/ownership·제한·환경·마일스톤과 release notes·migration·known issues·testing·troubleshooting을 실제 `fabric` 지원 범위에 맞췄습니다.
  - 지원 원장: 75개 identity 중 public 64개·HIL pass 62개입니다. QDEC20/21은 public/partial이며,
    나머지 system identity 11개는 근거에 따라 internal 또는 none입니다.
  - 검증: 생성 원본/문서, Host·CI·inventory·문서·style gate를 통과했고 과거 검증·공개 자산은 소급 변경하지 않았습니다.
  - 결선·증거: 새 flash·결선·물리 PASS 없음. [119번 기록](<./04_검증 기록/119_T17_문서와_지원_매트릭스_정리.md>)을 따릅니다.

- [x] **T18 — M27 정식 공개 절차 준비**
  - 완료 결과: `m27_stable_release.py`로 stable prepare·plan 검증·읽기 전용 사전점검·Release 게시·index 게시를 분리했습니다.
  - 차단 계약: 잘못된 version/commit, 미완료 technical gate, exact plan에 결합되지 않은 T22 승인, 기존 tag/Release/version과 asset byte 불일치를 거부합니다.
  - 검증: 과거 stable allowlist를 영구 변경하지 않는 실행 중 후보 구성과 승인 전 외부 명령 미호출을 unit/contract로 확인했습니다.
  - 결선·증거: 새 flash·결선·공개 작업 없음. T18 완료가 공개 실행 허가는 아닙니다. [120번 기록](<./04_검증 기록/120_T18_stable_공개_절차와_승인_차단.md>)을 따릅니다.

- [x] **T19 — RC 소스 고정과 전체 회귀 검사**
  - 완료 결과: exact Core/board/SDK/toolchain을 고정하고 Host·문서·inventory·35개 target build와 RC package 이중 재현성을 통과했습니다.
  - 해결 결과: T16 crypto object의 Windows 절대 경로가 261자가 되어 archive가 실패한 원인을 특정하고 출력 경로를 `C:\t`로 제한해 35/35를 재검증했습니다.
  - 변경 영향: 이후 문서·readiness 변경은 runtime package 입력에서 제외합니다. runtime source가 바뀌면 전체 target gate를 다시 실행합니다.
  - 결선·증거: 새 flash·결선 없음. [121번 기록](<./04_검증 기록/121_T19_RC_소스_고정과_전체_회귀.md>)을 따릅니다.

- [x] **T20 — RC 패키지 재현성·설치 수명주기 검증**
  - 완료 결과: 격리 Boards Manager 설치, lock/발견 목록 30/30 clean compile, 실제 pyOCD Upload, `0.3.0` 전환, 제거·재설치와 prerequisite 보존을 통과했습니다.
  - 해결 결과: Nordic 공식 URL의 같은 nRF Util version byte 변경은 서명·version을 확인해 새 exact hash로 고정했습니다. 저전력 firmware의 SWD `No ACK`는 under-reset/halt로 원인을 분리하고 정상 Upload했습니다.
  - 경계: 과거 `0.3.0` byte는 변경하지 않았고 과거 post-install을 현행 URL로 소급 검증하지 않았습니다. tag·Release·stable index도 쓰지 않았습니다.
  - 결선·증거: 새 GPIO 기능 시험 없음. 지정 CMSIS-DAP 1회 Upload. [122번 기록](<./04_검증 기록/122_T20_RC_설치_수명주기와_실제_Upload.md>)을 따릅니다.

- [x] **T21 — 정식 0.4.0 패키지 생성·최종 검사**
  - 완료 결과: 비공개 RC/stable package를 각각 두 번 생성해 byte 재현성을 확인했고 정규화 runtime payload가 같았습니다.
  - 설치 검증: 격리 Boards Manager stable 설치, 발견·clean compile 30/30, 대표 Blink 실제 pyOCD Upload를 통과했습니다.
  - 변경 영향: T19 이후 host hook 호환성을 보완하고 Host·계약·문서·inventory를 재검증했습니다. 이후 설치 예제 실행기와 문서 변경은 runtime 입력에서 제외됩니다.
  - 결선·증거: 기존 S/U 기능 시험은 반복하지 않았고 USB Upload 1회만 수행했습니다. tag·Release·공개 index는 만들지 않았습니다. [123번 기록](<./04_검증 기록/123_T21_stable_패키지와_최종_검사.md>)을 따릅니다.

## 7. D단계 — 공개와 마무리 (T22~T25)

- [ ] **T22 — 최종 결과 확인과 공개 승인**
  - 상태·선행: 조건부 사용자 승인 요건 충족 / 최종 exact stable plan hash에 승인 JSON 결합 중.
  - 할 일: 대상 commit/version·필수 검증·제외한 품질 측정·known limitations·공개할 자산을 사용자에게 제시한다.
  - 완료 기준: 해당 결과에 대한 프로젝트 소유자의 명시적 승인 근거가 기록된다. 42번 범위 조정이나 TODO 작성 요청을 최종 승인으로 취급하지 않는다.
  - 결선·증거: 불필요. 프로젝트 소유자가 T19~T21 무실패 완료 시 T22 승인과 T23~T25 진행을 명시했으며 조건 충족. 124번.

- [ ] **T23 — v0.4.0 태그·GitHub Release·자산 공개**
  - 상태·선행: 대기 / T21·T22, remote exact commit·기존 tag/asset 상태 확인.
  - 할 일: 승인한 commit에 tag를 만들고 검증된 asset·release notes를 공개한 뒤 stable index에 등록한다.
  - 완료 기준: 공개 commit·URL·크기·hash가 승인한 산출물과 일치하고 기존 공개 자산이 보존된다. 중간 실패는 상태 확인 후 안전하게 재개하며 같은 버전의 다른 bytes로 덮어쓰지 않는다.
  - 결선·증거: 불필요, 외부 공개 작업. 현재 공개 안 됨.

- [ ] **T24 — 공개 URL에서 최종 설치 검증**
  - 상태·선행: 대기 / T23.
  - 할 일: 새 격리 환경에서 실제 공개 index/archive를 받아 설치·build·upload·제거·재설치·전환을 확인한다.
  - 완료 기준: 로컬 staging/cache만으로 성공했다고 하지 않고 공개 다운로드의 version·hash·설치/실행 근거를 남긴다. 실패하면 최종 완료를 보류하고 공개 자산 불변 정책에 맞게 처리한다.
  - 결선·증거: 대표 upload는 USB 필요; 지정 기능 실행은 해당 결선. 공개 URL 검증 증거 미등록.

- [ ] **T25 — 최종 문서·커밋·푸시·CI·작업 폴더 정리**
  - 상태·선행: 최종 정리 대기 / T23·T24 및 미해결 항목 없음.
  - 할 일: 공개 결과·release identity·검증 기록·README·로드맵을 마무리하고 commit/push·최신 CI를 확인한다. 보존할 증거와 재생성 가능한 임시 출력물을 분리한다.
  - 완료 기준: 근거가 영구 보존되고 남은 이슈/프로세스/미추적 변경이 설명되며 재개할 누락 작업이 없다. 정리는 정확히 확인한 작업 경로만 대상으로 한다.
  - 결선·증거: 문서·정리에는 불필요. TODO 보관/삭제는 10절을 따르며 자동으로 함께 삭제하지 않는다.

## 8. 남은 release gate와 TODO 연결

### 남은 작업 순서

| 순서 | 단계 | 완료해야 하는 결과 |
| --- | --- | --- |
| 1 | T22 | exact 결과·공개 자산에 대한 프로젝트 소유자 승인 |
| 2 | T23 | 승인한 tag·Release asset·stable index 공개 |
| 3 | T24 | 공개 URL 설치·build·Upload·제거·재설치·전환 검증 |
| 4 | T25 | 최종 기록·커밋·푸시·CI 확인과 정확히 식별한 임시 산출물 정리 |

이는 남은 순서이지 이번 문서 정비에서 실행한 작업 목록이 아닙니다. T16 이후 release gate의
작업량이 동일하지 않으므로 S의 58조건이나 완료한 T 번호 개수로 v0.4.0 전체 진행률을
계산하지 않습니다. T13의 합의한 S/U 범위는 100%이며 정식 릴리스는 미완료입니다.

### 기계 판정 gate

| Readiness gate | 연결 작업 | 현재 판정 |
| --- | --- | --- |
| `m24_fixture_hil` | T04·T07~T11·T13~T15 | **PASS** |
| `m25_fixture_hil` | T05~T10·T12~T15 | **PASS**; QDEC20/21은 partial 근거를 명시한 공개 지원 |
| `host_regression`, `documentation`, `zephyr_repro_build` | T16~T19, T21의 변경 영향 재검증 | **PASS**; runtime 변경 시 재실행 |
| `package_reproducibility` | T20·T21 | **PASS**; RC/stable 이중 재현과 runtime 동등성 확인 |
| `boards_manager_lifecycle` | T20·T21; 공개 후 검증은 추가로 T24 | **PASS**; RC/stable 로컬 설치 완료, T24 공개 URL은 별도 |
| `project_owner_approval` | T22 | human HOLD; 사용자 승인 의사는 확인됐고 최종 exact plan SHA-256 결합 중 |

M23·후보 source/build·기본 onboard·M26 판정·기존 자산 불변 gate의 근거는 기존 ledger에 있다.
M24/M25 physical gate는 T15 증거 대조로 PASS가 됐고 나머지 state는 유지한다. 실기 PASS와 RC 통과·정식 공개,
정식 공개와 공개 URL 검증 완료를 각각 구분한다.

## 9. 매 작업 종료 시 남길 인계 내용

2절 체크포인트를 갱신하고, 실제 결과는 검증 기록에 추가한 뒤 관련 T 항목의 `증거`에 링크한다.
새 컨텍스트에서 직전 명령을 무작정 다시 실행하지 않도록 다음 정보를 남긴다.

- 수행한 T 번호와 완료/부분/실패, 변경 파일과 commit·push 상태.
- 실행 명령, exact source/board/image hash, 결과·log/evidence 경로, 실제 시험과 mock의 구분.
- 중단 사유, 살아 있는 프로세스/세션, 보드 role·마지막 image·COM·스위치·결선 상태.
- 다음에 할 **구체적 한 행동**, 선행조건, 사용자가 해야 할 결선·재연결·승인.
- 재사용 가능한 build/cache의 identity와 재검증 범위. Commit/hash가 다르면 이전 성공을 이어 붙이지 않는다.
- CI run URL·대상 commit·확인 시각·상태. 미완료 run을 완료로 적거나 확인 없이 background 작업을 약속하지 않는다.

## 10. TODO 보관·삭제 조건

현재는 활성 문서이므로 삭제하지 않는다. 기본은 완료 후 보관이며, 사용자가 허용한 정리 범위에서
다음 조건을 모두 충족하면 archive 또는 삭제할 수 있다.

1. T01~T25 전체 완료와 정식 공개 URL 검증이 끝났고, 재개할 작업·미해결 문제·사용자 요청이 없다.
2. 결정·제한·최종 지원 matrix·명령·실제 증거·공개 identity가 영구 문서에 옮겨져 TODO가 유일한 근거가 아니다.
3. 삭제/이동 대상은 **이 TODO 파일**로 특정한다. 검증 기록·readiness 참조·공개 asset·SDK·사용자 파일은 포함하지 않는다.
4. [루트 작업 지침](../AGENTS.md), README, 문서 안내, 로드맵, RC·도구 안내 등 들어오는 링크를
   같은 변경에서 최종 기록 또는 보관 위치로 바꾸고 문서 검사를 통과한다.
5. 정리 결과와 Git 복구 가능 여부를 남기고 commit/push한다. 미완료 체크를 지워 완료처럼 보이게 하지 않는다.
