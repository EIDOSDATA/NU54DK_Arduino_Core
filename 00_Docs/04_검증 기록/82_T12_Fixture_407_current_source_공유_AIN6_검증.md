# T12 Fixture 407 — current-source 공유 AIN6 검증

| 항목 | 값 |
| --- | --- |
| 문서 ID / 개정 | NU54-T12-F407-001 / 1.0 |
| 작성일 | 2026-09-07 (Asia/Seoul), 원본 시각은 UTC |
| Exact Core source | `4a64c2562fdd5e9169faecf56b43043a0afec67c` |
| Board gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| Fixture catalog | revision 5, ID 407 |
| 결과 | SWD **10 MHz**, 첫 실행 **12개 기능 PASS**, 연속 campaign 7.141초 |
| 다음 작업 | **408/AIN7 재결선·사용자 확인**, T12 전체는 부분 완료 |

사용자의 “ㅇㅇ 그대로야” 답변을 2026-09-06T14:55:35Z에 기록하고, 확인 유효시간 안에
exact pair image를 빌드·확인한 뒤 407을 실행했다. 실기 재시도는 없었다. 7.141초는
campaign 시간이며 준비·빌드·업로드 시간은 포함하지 않는다.

## 결선과 시험 조건

| 역할 | GPIO 및 조건 |
| --- | --- |
| A DUT, role 1 | **P1.13/AIN6(P4-11)**, 버튼을 누르지 않은 공유 입력 |
| B peer, role 2 | **P1.14(P4-12)**, INPUT 내부 pull-down → pull-up → pull-down |
| 공통 GND | A P2-30 ↔ B P2-30 |
| 연결 상태 | DAP UART 양쪽 분리·SWD 연결, 기존 SB/PMIC 유지, 이전 A P1.12 신호선 제거 |

USB 분리 후 결선·재연결의 이전 확인은 2026-09-06T13:47:49Z이며 이번 답변은 동일 조건의
유지를 확인했다. [checkpoint](evidence/t12-fixture407-4a64c25/checkpoint.json)와 [confirmation](evidence/t12-fixture407-4a64c25/confirmation.json)에 보존했다.
A P1.13은 SW1 net/물리 SW2 버튼과 공유하므로 버튼 미누름 상태만 검사했다.
B P1.14의 LED4 net은 R34 330Ω을 거쳐 U9B NC7WZ17P6X 입력에 연결된다.
이번 신호원은 출력 드라이버나 PWM을 켜지 않고 입력 바이어스만 바꿨다.
각 단계에서 25ms 정착 후 manual SAADC 2ms 간격·12bit·gain 1/4·oversample 1을 사용했다.

## Source·software·target 근거

이전 [81번 software 검증](81_T12_Fixture_407_Host_재개와_검증.md)은 source 393e419에서
Host **655 PASS·1 조건부 SKIP(총 656)**, 관련 113·계약 45·package 20·정렬 358·Inventory·예제 발견,
pair/BLE target 8/8을 완료했다. 이번 source 4a64c25까지의 전체 Git 차이는 문서·역사 증거뿐이며
[software 입력 비교](evidence/t12-fixture407-4a64c25/software-input-comparison.json)에서 제품·build·runner·Host 코드 차이 0을 확인했다.
기존 결과를 새 실행으로 세지 않고 이전 source에 유지했다. Windows 보안 정책 변경은 없다.

이번에는 actual clean HEAD의 pair DUT/peer를 `C:/u3p`에 새로 빌드해 **2/2 PASS**, 오류·경고 0,
117.38초를 확인했다. NCS v3.4.0 revision `99553055607b2e9885fbc80ccd11fa9da81c2df0`,
Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`, bundle `dcbdc366a1`을 유지했다.
각 역할의 repository translation unit 42개·정규화 설정·전체 source 소속은 이전 준비 pair와 동일하다.
[입력 비교](evidence/t12-fixture407-4a64c25/build-input-comparison.json), [target 기록](evidence/t12-fixture407-4a64c25/target-build-evidence.json),
[artifact index](evidence/t12-fixture407-4a64c25/target-artifact-index.json)가 실제 source·HEX/ELF·설정을 연결한다.

| 역할 | 실제 HEX SHA-256 | 실제 ELF SHA-256 |
| --- | --- | --- |
| A / 1 | `c3d9fe97d507bc0db669d32889cfb849762dae0ded5e9bdda11c995006a98b23` | `1f46f1c55ce03e6c061508d653599a2a3940b137d7cd0145109c568dc6d63d3a` |
| B / 2 | `e2c2a51c801efe2354a91cc3f39b0732a79feb674539c80b0e9cfe5d761fa198` | `ad600d976320a50cf4f4b2c4c4dd5515bc97fd98b4feb0eeae68dad2830b8a50` |

## 실제 결과와 독립 감사

32/256 sample 길이 × single/double DMA buffer × LOW/HIGH/LOW의 12개 vector를 모두 실행했다.
모든 LOW는 -256~512, 모든 HIGH는 1024 초과~4095 기준을 만족했다.

| 길이 / buffer | 단계별 samples | LOW 전 / HIGH / LOW 후 median | 세 단계 전체 min / max |
| --- | --- | --- | --- |
| 32 / 1 | 32 | 0 / 3752 / 0 | -12 / 3764 |
| 32 / 2 | 64 | 0 / 3752 / 0 | -12 / 3764 |
| 256 / 1 | 256 | 0 / 3752 / 0 | -20 / 3764 |
| 256 / 2 | 512 | 0 / 3752 / 0 | -16 / 3768 |

총 **2,592 samples**, LOW 범위 -20~12, HIGH 범위 3740~3768이다. 각 원본 sample의 개수·hash,
DMA 상태·GPIO 입력 모드·phase 전환을 [독립 감사](evidence/t12-fixture407-4a64c25/results-audit.json)로 대조했다.
GPIO 입력 readback 24회는 raw mask `0xF0F`에서 LOW `0x4`·HIGH `0xC`이며,
cleanup 12회 모두 B→A 정지를 확인했다. B의 해제 readback 12회는 INPUT no-pull raw 0이다.
기능 12개·cleanup 12개·campaign 관리 2개의 총 26개 journal record가 최종 JSON과 순서까지 일치한다.

| 원본 | 원본 byte SHA-256 |
| --- | --- |
| [JSON](evidence/t12-fixture407-4a64c25/fixture407-attempt1.json) | `d780728ece2e30c8fb724912c23764c50ce944fb1fe76553c51d9c8192b9d602` |
| [journal](evidence/t12-fixture407-4a64c25/fixture407-attempt1.json.jsonl) | `cd1c437662243181edd028276acaa6a8bf900e2836b76f310a8255c52969c598` |

[실행 log](evidence/t12-fixture407-4a64c25/fixture407-attempt1.log)의 `V04_SIGNAL_PASS=two-board-synthetic-signal`과
[실행 wrapper](evidence/t12-fixture407-4a64c25/run.py)를 함께 보존한다. SWD 10,000,000Hz, 지정 두 probe, sector erase,
`auto_unlock=false`를 사용했다. UID 원문은 공개 증거에 남기지 않고 SHA-256 식별을 유지한다.

2026-09-06T15:01:03.549747Z의 [읽기 전용 postflight](evidence/t12-fixture407-4a64c25/postflight.json)는 추가 flash/reset/fixture
명령 없이 두 보드의 full source 4a64c25·role·protocol과 CPUID `0x411fd210`을 확인했다.
관측 당시 양쪽 상태는 SLEEPING이었다. 이 관측을 장시간 안정성 검증으로 확대하지 않는다.

## 보존·완료 경계와 다음 결선

[원본 manifest](evidence/t12-fixture407-4a64c25/raw-files.json)의 입력 **33개**는 UTF-8 LF 사본과 원본 byte gzip으로 보존했다.
원본 gzip 복원·SHA-256·UID 원문 부재와 Git stage byte 일치를 검증한다. 이전 80번 차단·81번 준비
기록과 모든 이전 실기 증거는 변경하지 않는다. 현재 image·log·재현용 입력은 필요한 증거이므로 유지한다.
최종 [문서 검사](evidence/t12-fixture407-4a64c25/docs-verification.json)는 Markdown **191개 PASS**를 기록한다.
진행 중 시험 프로세스가 없는 것을 확인한 뒤 문서·증거를 commit하고 main에 push한다.

[누계 감사](evidence/t12-fixture407-4a64c25/analog-coverage-audit.json)는 이전 401~406 원본 gzip의 hash와 기능·cleanup·DMA count를
대조했다. 각 exact source를 구분한 401~407 합계는 **228개 기능·49,248 samples·228개 cleanup**이다.
AIN0~6의 개별 기능 근거이며 408/AIN7은 아직 미실행이다. 버튼 동작·debounce·wake,
교정 전압·정밀 ADC, PWM period/duty capture, 전체 T12·T13 이후의 완료를 뜻하지 않는다.
Readiness 필수 16개 중 미해결 8개를 유지한다. 후속 catalog는 **420 QDEC·430 I2S·440 PDM**이며
79번 다음 단계 문장의 420/440 이름은 반대로 기재된 과거 안내다. 실제 catalog를 기준으로 진행한다.

다음 408은 양쪽 USB를 분리하고 A 쪽 신호선을 **P1.13에서 P1.14/AIN7(P4-12)**로 옮긴다.
B **P1.14(P4-12)**와 공통 GND는 유지한다. 최종 결선은 **A P1.14 ↔ B P1.14, GND ↔ GND**다.
DAP UART 분리·SWD 연결·기존 SB/PMIC를 유지하고 USB를 재연결한 뒤 별도 사용자 확인을 받는다.
이번 작업에서 408 명령은 실행하지 않았다. 후속 문서 HEAD는 실제 407 업로드 source와 구분하고,
408 실행 시 clean HEAD의 exact pair image를 새로 준비한다.
