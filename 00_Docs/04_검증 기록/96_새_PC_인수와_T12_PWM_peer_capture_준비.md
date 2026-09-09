# 새 PC 인수 확인과 T12 PWM peer capture 첫 경로 준비

> 과거 검증 이력입니다. 준비·다음 작업·실행 조건은 기록 당시 기준이며, 현재 상태는 [v0.4.0 TODO](../TODO_v0.4.0.md)를 따릅니다.

2026-09-07. 인계 commit `f42bda55f7b45f7af0a347ecf5f1f516bb34eb6a`를 새 PC의 실제
저장소에서 확인하고 기존 작업을 보존했다. PWM peer capture 첫 측정 경로를
`59282818fc3733dae4b247a8942069955eabc2df`로 고정했다. **새 PC 외부 신호 실기는 NOT RUN이며,
T12 전체·T13 이후·R14·RC·정식 공개와 readiness 미해결 8 개는 유지한다.**

## 인수 확인

- 실제 저장소는 `C:/Users/eidos/GitHub/NU54DK_Arduino_Core`, branch는 main이다. 첫 status는
  clean이었고 origin URL·인계 SHA를 확인했다. fetch 뒤 `merge --ff-only origin/main`은
  Already up to date였다. submodule sync/update 뒤 board gitlink는
  `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`이며 미커밋 변경이 없다. reset/clean은 하지 않았다.
- AGENTS, TODO 전체 373줄, 다른 PC 인계, 94·95번, 41·42번, 기능 시험표와 HIL/환경 안내를
  읽었다. R00~R13과 source별 T11 완료, PWM 미시작 STOP 수정, 두 보드 무점퍼 결과를 보존한다.
- f42bda5의 [Software Gates](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/34096227435) 7/7과
  [Reproducible Builds](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/34096227297) 8/8을 이번 PC에서 SUCCESS로 확인했다.
  이는 8281661의 기존 15 개 SUCCESS와 별도 push의 결과다.
- 초기 USB 열거는 probe 0 개·COM 0 개였다. 이후 사용자 연결 보고에 따라 08:14:24Z 다시 열거해
  정확한 A/B hash의 probe 2 개·COM 4 개를 확인했다. A는 COM12/13, B는 COM14/15다.
  08:18:14Z 두 exact UID의 배타 lock을 잡고 SWD 10 MHz attach에서 CPUID `0x411fd210`을
  각각 읽었다. 두 CPU 모두 읽기 전후 SLEEPING이었다. reset/halt/resume/flash 명령이나 외부
  신호 시험은 실행하지 않았다. UART 데이터·현재 firmware identity/READY·핀 상태는 미검사다.
  초기 감사 JSON의 장치 0 개는 그 시점 관측이며 아래 후속 관측과 구분한다.
- 첫 읽기 진단은 기본 PATH의 Python/DLL 혼합으로 ctypes import 단계에서 실패해 probe를 열지
  못했다. NCS 전용 자식 환경을 적용한 실행이 위 결과다. 보안 정책이나 설치 파일은 바꾸지 않았다.

## 새 PC 환경과 검사

Python 3.12.10과 Arduino CLI 1.5.1은 기존 설치가 없어 버전 고정 winget 설치를 수행했고
installer hash 검사를 통과했다. Host `.venv`에는 requirements-host.txt의 hash 고정
PyYAML 6.0.3을 설치했다. 기존 Python 3.14·SDK·board·보안 설정은 유지했다.

기존 WinLibs **GCC 16.1.0 MCF/UCRT r1**과 LLVM **LLD 22.1.8**을 Host에 선택했다.
이는 예전 PC의 POSIX r4나 원격 GCC 15.2/LLD 20.1.8과 다른 실제 조합이다.
Host 전용 두 flag JSON 배열은 `["-fuse-ld=lld"]`이며 target에는 적용하지 않았다.
CMake/Ninja와 target Python 3.12.4·pyOCD 0.42.0은 고정 `dcbdc366a1` bundle을 사용했다.
NCS/Zephyr HEAD는 lock의 `99553055607b2e9885fbc80ccd11fa9da81c2df0` /
`bf801e4e3d19e1ffa76164346480cb7734dd2800`이다. 두 SDK checkout의 status도 clean이었다.

PowerShell `verify-nordic.ps1`의 직접 실행은 현재 script execution policy로 거부됐다.
원문 오류를 환경 evidence에 보존했으며 정책·허용 목록·SDK 내부 파일을 변경하지 않았다.
기존 ready marker의 재사용을 이번 설치 검증으로 주장하지 않는다. 실제 revision·도구 실행,
exact NCS inventory/serial 계약과 target build의 성공을 각각 별도 근거로 남긴다.

최초 baseline Host는 85 그룹 **680 PASS·2 조건부 SKIP**였다. 한 SKIP는 설치본 CLI 발견용
환경 조건이고 다른 하나는 검사 도중 TODO 준비 기록을 추가한 dirty checkout 조건이다.
기존 suite 코드에서 수행한 결과이며 추가한 PWM 7 개를 포함하지 않는다. baseline pair는
새 PWM main/CMake 변경 전에 완료된 **2/2 build-only**다. 새 기능의 결과로 재사용하지 않는다.

최종 **clean exact 5928281**의 결과는 다음과 같다.

| 검사 | 결과와 범위 |
| --- | --- |
| canonical Host | 86 그룹·688 PASS·1 조건부 SKIP(설치 package용 M13 CLI 발견); 새 PWM 7 개 포함 |
| contract / package | 45 PASS / 20 PASS |
| docs / inventory | Markdown 206 개 PASS / 75 identity·23 serial과 generated/readiness 계약 PASS |
| exact NCS | M23 75·M24 23 identity/23 profile, onboard 7/fixture 16 계약 PASS |
| examples | Arduino CLI 1.5.1의 표준/custom 예제 발견 PASS; 설치 29 개 compile 결과로 확대하지 않음 |
| C/C++ 정렬 | clang-format 22.1.8·first-party 373 개 PASS |
| PWM pair target | 2/2 build-only, 108.72 초; 두 role ELF/HEX·build record·mailbox identity 대조 |
| 새 PC 실제 장치 | 후속 probe 2·COM 4, exact UID SWD 10 MHz CPUID 읽기 2/2 PASS; flash/외부 HIL NOT RUN |

Core/libraries/variants/Zephyr/tool/board 입력은 f42bda5와 Git 차이가 없다. 변경 범위는 HIL·Host
판정기와 문서다. 제품 61 개 target·29 개 설치 예제의 역사 결과를 이번 PC의 결과로 재표시하지 않는다.

- [검사 합계·source·CI·artifact hash 감사](evidence/new-pc-pwm-capture-5928281/audit.json)
- [실제 도구 버전·hash·원본 실행 정책 오류](evidence/new-pc-pwm-capture-5928281/new-pc-environment.json)
- [정규화 로그와 원본 gzip의 SHA 목록](evidence/new-pc-pwm-capture-5928281/raw-files.json)
- [DUT/peer ELF·HEX identity](evidence/new-pc-pwm-capture-5928281/pwm-exact-images.json)
- [현재 USB·COM 열거](evidence/new-pc-pwm-capture-5928281/current-usb.json) / [현재 SWD 읽기](evidence/new-pc-pwm-capture-5928281/current-swd.json)

ELF/HEX·compile DB는 이 PC `C:/pwc04`에 보존하고 크기/SHA를 기록했다. baseline `C:/pcv04`,
최초 실패 `C:/pwm04`도 남겨 두었다. 큰 artifact를 Git에 넣거나 임시 경로를 삭제하지 않았다.
후속 문서 207 개 UTF-8/local-link와 원본 71 개·정규화 사본·gzip의 SHA 대조도 통과했다.
이 문서·증거 commit 이후 자동 CI는 해당 push SHA의 새 실행이며, 위 f42bda5 결과와 구분한다.

## 첫 PWM capture 구현 범위

기존 Fixture 408의 **B GPIO P1.14 → A GPIO P1.14, GND ↔ GND** 경로를 별도
`--pwm-capture` 모드로 사용한다. 핀·공유 LED buffer의 기존 408 승인 범위를 확장하지 않았다.
B PWM20/21/22 × slot 0~3 × TOP 1000/4000 × duty 0/25/50/75/100% × DMA bit15
극성 두 가지, 총 **240 개 준비 vector**다. Individual load, 4 values, CPU start, loop에 한정한다.
PwmSequenceConfiguration의 idle inversion과 DMA word bit15 극성을 혼동하지 않는다.

A는 GPIOTE20 channel 0→DPPI20 channel 0→TIMER22 CC0 1 MHz의 하드웨어 capture를 사용한다.
CPU는 이벤트·CC·level을 읽고 timestamp를 만들거나 IRQ를 마스킹하지 않는다. 201 개 에지로
100주기 각각의 period와 HIGH 비율을 검사한다. 주기는 목표의 ±5%, duty는 목표 비율의
상대 ±5%이며 평균으로 개별 이상을 숨기지 않는다. 0/100%는 100주기에 해당하는 시간 동안
에지 없음과 정적 level을 확인한다. 이 기능 기준은 절대 clock 교정·jitter 보증이 아니다.

원본 status·에지는 PASS 판정 전에 observation으로 저장한다. 정상 protocol 안의 측정 timeout도
partial raw를 읽고 STOP할 수 있다. 오류/누락/중복/역순/비교 경계/guard/짧은 정적 관측과
잘못된 CLI 조합을 거부하는 Host 7 개를 추가했다. B 출력 STOP 뒤 A capture 자원을 반환하며,
STOP 실패 시 fault latch·lease를 보존한다. 다른 기존 fixture가 점유한 동안 새 arm은 거부한다.

외부 제어는 기존 exact source/board/image·UID·배타 lock·sector flash·`auto_unlock=false`·
controlled reset/start를 유지한다. 이 모드는 SWD **10 MHz**·유한 campaign만 허용하며
기본은 preflight-only다. 각 case 전에 현재 30 분 이내의 결선 confirmation을 재검사한다.

첫 초안 target은 DUT build 성공·peer build 실패였다. GCC가 role 2에서 초기 null로 유지되는
수신 handle 경로에 `-Werror=nonnull`을 보고했다. 자원 반환의 owner flag와 포인터를 함께
검사하도록 교정했으며 첫 실패 원본은 유지한다. 제품 Core/SDK 결함이나 물리 FAIL로 바꾸지 않는다.

## 다음 실제 행동과 남은 조건

1. 현재 USB·A/B hash·SWD 읽기 확인을 완료했다. 최신 exact clean source의 pair image를
   준비하고 실제 실행 직전 두 UID가 여전히 연결됐는지 다시 확인한다.
2. 두 USB를 분리하고 **B GPIO P1.14→A GPIO P1.14, 공통 GND**만 연결하도록 안내한다.
   DAP UART 양쪽 분리·SWD 연결, 동일 I/O 전압·전원 레일 비연결·기타 출력 없음과 재연결 완료를
   현재 사용자에게 확인받은 뒤 새 confirmation을 만든다. 이전 COM이나 408 확인을 재사용하지 않는다.
3. 먼저 이 240 vector의 실제 capture 성립을 확인한다. 이후 common/grouped/wave-form,
   32/256 values, sequence0/1 순서·유한 end/repeat, DPPI START, triggered-step과 idle inversion을
   확장한다. 94번의 내부 lifecycle 결과나 이번 준비로 이 외부 모드가 PASS한 것은 아니다.
4. GPIO/GPIOTE는 승인 pin/가용 channel의 edge·level·task/set/clear·누출과 예약 거부가 남는다.
   I2S prepare는 이미 1024 word 용량을 받지만 vector는 32/256이고 I2sFiniteTransfer는 유한
   payload다. 100 연속 buffer와 TX-only/RX-only 제출·수신 판정을 별도로 확장한다.
5. QDEC firmware가 1000 cycle/10 ms를 받더라도 현재 vector는 1/100 cycle·2 ms다. 실행 중 역전,
   read/clear/restart·invalid transition·10 회 반복과 긴 case의 lease/timeout 설계가 남는다.
   TIMER 95번의 compare 10 회/조합을 전체 요구의 1000 event로 확대 해석하지 않는다.
6. 440 PDM의 기본·연속 PASS는 보존하며 재결선을 요구하지 않는다. 해당 T12 단독 결과 뒤 T13의
   오류/충돌/600 초·7200 초 soak, 이후 통합·RC·공개 절차를 유지한다.

이 기록은 첫 capture 경로 준비와 후속 USB/SWD 읽기 확인의 체크포인트다. HIL 실행이나 background
작업을 예약하지 않았고 T12 전체·T13 이후·RC·정식 공개 완료로 처리하지 않는다.
