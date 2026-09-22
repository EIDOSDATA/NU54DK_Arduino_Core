# 개발 인계 — M31 Windows 릴리스와 메모리 최적화 우선

현재 설치·지원 배포는 **v0.4.1**, 개발 소스 식별자는 **0.4.1-dev**입니다.
2026-09-21 사용자 결정으로 **M31 완료 후 v0.5.0 Windows 릴리스**를 준비합니다.
M32/M33과 Ubuntu/macOS 지원은 후속 버전(미정)이며 HOST-W04~W08은 계속 보류합니다.

문서 정비 후 별도 사용자 요청으로 **main의 미공개 개발 이력을 마일스톤별로 정리**했습니다.
현재 재개 기준은 `main`입니다. 다음 개발 브랜치 이름은 **`M31-MEM-OPT`**이며, 이번 이력 정리
직전에는 로컬·원격 모두 존재하지 않아 재생성하거나 다른 브랜치를 삭제하지 않았습니다.
이후 실제 `M31-MEM-OPT`에서 P0 구현을 시작했습니다. Release 공개는 수행하지 않았습니다.

후속 설명 통합 요청은 [메모리 최적화 통합 설계](<01_아두이노 코어 설계/21_M31_메모리_최적화_통합_설계.md>)로
문서화했습니다. 링크 GC만으로 모든 자원을 제거한다는 해석, local static의 lazy allocation 표현과
확정 절감량 주장을 정정했습니다. 초기 문서-only 개정 뒤 현재 branch에서 구현을 이어갑니다.
최신 목표는 **동등 기능 nRF native + 우리 API의 최소 필수 비용**입니다. 선언 기반 최적화를
차기 기본 경로로 만들고 full은 명시적 호환 선택지로 보존합니다. 실제 기본값 변경은 아직 하지 않았습니다.
일반 Core API는 compiler-assisted capability probe로 도달 가능한 참조를 판정하고, library의 간접
의존성과 공개 BLE role/capacity 선언을 합쳐 `prj.conf`·overlay·source/init를 생성하는 설계입니다.
따라서 `adaptive` profile에서 `SPI.begin()`은 수동 `prj.conf` 없이 SPI 준비로 연결됩니다. P0-1의
capability registry·공개 declaration schema·library 요구·transitive resolver와 compiler-assisted
probe engine을 builder link/cache에 연결했고, 결정적 `resolved-capabilities.json`에서 미선택 Kconfig
OFF·선택 Kconfig·기능별 overlay·기존 CMake source gate를 합성합니다. final `.config` override는
fail-closed로 거부합니다. Serial-only·SPI include-only·Serial+SPI clean build에서 capability·Kconfig·
Devicetree chosen·`SPI.cpp` 포함/부재와 동일 입력 cache 재사용을 확인했습니다. 기존 `standard`는
기본 full 호환 profile이며 `adaptive`는 아직 실험 선택지입니다. 역할 capacity 집계값은
registry schema v4에서 `BT_MAX_CONN`·ISO channel·
L2CAP TX MTU·`BT_MAX_PAIRED` Kconfig로 생성되며 capability의 고정값과 충돌하면 resolver가 거부합니다.
`requires_any_role`은 역할 종속 capability에 허용된 role이 하나도 없거나 registry가 정의되지 않은
role을 참조하면 중단합니다. 따라서 BLE library를 role 없이 adaptive 구성에 넣는 경로를 이후 preset
연결 단계에서 조용한 full fallback 없이 차단할 수 있습니다.
feature schema v3는 기존 호환 profile에서 `conf`·`overlays`를 사용하고 resolved profile에서는 별도의
`resolved_conf`·`resolved_overlays`만 사용합니다. BLE의 기존 broad fragment는 호환 경로에 보존되며
adaptive 경로로 자동 유입되지 않습니다. 선택된 mode의 fragment hash만 cache 입력에 기록합니다.
기존 검증 설정에서 GAP/NUS·GATT/NUS·LE CoC·CIS central·Audio unicast source/sink·DF beacon/responder·
CS RAS initiator/reflector 10개 초기 role preset을 registry에 연결했습니다. 이 preset들은 서로의 임의
동시 선택을 거부하고 connection·ISO stream·ATT MTU capacity를 생성합니다. Channel Sounding library도
누락됐던 builder allowlist에 추가했습니다. registry schema v4의 `source_roots`와 capability별 `sources`는
Arduino가 선택한 library 안에서도 미선택 역할 translation unit을 CMake 입력에서 제외하고 그 목록과
hash를 provenance에 남깁니다. 손상된 source 해석 경로는 platform 밖으로 나가지 못하게 fail-closed로
거부합니다. 초기 10개 preset에 CIS peripheral·BIS source/receiver·encrypted/time 변형과
CIS-to-BIS peer/bridge/receiver 10개를 더해 총 20개 preset, ISO library 기준 11/11 역할을 연결했습니다.
ISO는 공통 facade와 역할에 필요한 RawCis/RawBis backend만 남깁니다. 새 작업 경로의 저수준 설정 없는
11역할 clean smoke에서 capacity·최종 Kconfig·source 포함/부재를 모두 확인했습니다. 여기에 Audio BAP
공개 예제 9개를 표현하는 7개 role preset을 더해 총 27개 preset을 연결했습니다. BAP도 공통 Audio facade와
unicast/broadcast 역할별 backend만 남기며, 저수준 설정 없는 9역할 clean smoke를 통과했습니다. sink-only
unicast image는 source ASE/PAC를 제외해도 compile되도록 선택적 PAC Source 초기화를 조건부로 고쳤습니다.
HAP server/client 2개 preset도 추가해 총 29개 preset을 연결했습니다. 실제 공개 HAP `.ino`를 복사하되
저수준 `prj.conf`는 사용하지 않는 clean smoke에서 capacity·최종 HAS Kconfig·source 포함/부재를 확인했습니다.
Security feature는 adaptive capability를 제공하며 pairing·bond·ZMS settings source만 남기고 BAS·DIS·HID·HRS를
제외합니다. 전역 소멸자가 있는 실제 sketch를 처리하도록 compiler probe의 `__dso_handle` 분석 stub도 고정했습니다.
Audio Control device/controller 2개 preset도 추가해 총 31개 preset을 연결했습니다. 실제 공개 `.ino`의
저수준 설정 없는 clean smoke에서 VCP·MICP, AICS 2개, VOCS 1개, connection capacity와 역할별 backend만
남는 것을 확인했습니다. Media Control player/client 2개 preset도 추가해 총 33개 preset을 연결했고,
공개 `.ino`의 저수준 설정 없는 clean smoke에서 MPL/MCS·MCC/OTS와 역할별 backend만 남는 것을
확인했습니다. Call Control server/client 2개 preset을 더해 총 35개 preset을 연결했고, 공개 `.ino`의
저수준 설정 없는 clean smoke에서 CCP/TBS와 Call Control backend만 남는 것을 확인했습니다. M31 인접
CAP acceptor/commander/initiator와 unicast acceptor/initiator 5개 preset도 추가해 총 40개 preset을
연결했습니다. 실제 공개 CAP `.ino`의 저수준 설정 없는 clean smoke에서 역할별 CAP backend와 필요한
broadcast sink 또는 unicast server backend만 남는 것을 확인했습니다. broadcaster-only CAP initiator가
불필요한 GATT를 요구하지 않도록 `BLEDevice.begin()`의 GATT callback 등록도 연결 기능에 한정했습니다.
CSIP set member/coordinator 2개 preset도 추가해 총 42개 preset을 연결했습니다. 실제 공개 CSIP `.ino`의
저수준 설정 없는 clean smoke에서 역할별 CSIP backend와 Security source만 남고 member 1개·coordinator
2개의 connection/bond capacity가 생성되는 것을 확인했습니다. PBP source/sink 2개 preset을 추가해
Public Broadcast 조합 backend와 필요한 CAP/Broadcast backend만 남는 것을 확인했습니다. TMAP
gateway/terminal/broadcaster/receiver 4개 preset까지 총 48개 preset을 연결했고, 실제 공개 `.ino` clean
smoke에서 역할별 unicast/broadcast backend만 남는 것을 확인했습니다. gateway/terminal의 pairing API는
비영구 구성으로 분리해 settings/ZMS/flash를 제외했습니다. GMAP gateway/terminal/broadcaster/receiver
4개 preset도 추가해 총 52개 preset을 연결했고, 공개 `.ino` clean smoke에서 역할별 backend와
connection/ISO/bond capacity를 확인했습니다. GMAP clean ELF 감사 중 비활성 periodic report/PAwR
response queue 4,472 byte가 공통 GAP translation unit에 남는 것을 발견해 Kconfig 경계 안으로 옮겼고,
Gateway 정적 RAM 예약은 82,543 byte에서 78,071 byte로 줄었습니다. builder는 이제 최종 `.config`·
Devicetree·source manifest·ELF·map과 adaptive capability 결과의 SHA-256, FLASH/RAM region·절대 사용량·
headroom·상위 RAM symbol 32개를 artifact manifest에 기록합니다. adaptive image에는 75% 경고·85%
실패 정책과 비활성 scan/periodic/PAwR queue 금지 symbol gate를 적용합니다. 후속 감사에서는 Observer가
꺼진 GMAP Terminal에 scan 결과 queue 2,540 byte가 남는 것을 검출해 같은 Kconfig 경계로 옮겼고,
정적 RAM은 73,047 byte에서 70,507 byte로 줄었습니다. Observer가 필요한 다른 GMAP 3역할은 queue와
기능을 유지했습니다. 그 다음은 `GapContext`의 extended advertising·periodic advertising·periodic
sync·PAwR 상태를 각 Kconfig에 맞춰 조건부로 배치했습니다. 새 GMAP 4역할 clean build에서
Terminal과 Gateway의 `GapContext`는 2,224 byte에서 320 byte로 줄었고 정적 RAM은 각각
68,603 byte와 76,167 byte가 됐습니다. `EXT_ADV+PER_ADV_SYNC`가 필요한 Receiver는 912 byte,
`EXT_ADV+PER_ADV+PER_ADV_SYNC`가 필요한 Broadcaster는 1,184 byte의 context를 유지하며 정적
RAM은 각각 75,810 byte와 77,743 byte입니다. 네 역할 모두 금지 symbol은 0건입니다. 새
TMAP 4역할은 62,020~83,546 byte, 초기 BLE/ISO/Audio/DF/CS 대표 10역할은
35,576~91,037 byte의 정적 RAM으로 fresh build를 통과했고 모두 금지 symbol 0건입니다.
초기 10개, ISO 11개, BAP 9개, HAP·Control·Media·Call 8개, CAP 5개, CSIP·PBP 4개,
TMAP·GMAP 8개를 합친 55개 고정 image에 검증값보다 약 1~2 KiB 높은 clean-example RAM
상한을 smoke gate로 고정했습니다. 금지 symbol은 advanced GAP queue에서
NUS·GATT·CoC·Security 전용 저장소까지
확대했습니다. fresh 검증에서 Central 역할이면 최종 Kconfig가 강제하는 Observer를 GAP/NUS·
GATT/NUS·CoC·CS initiator declaration이 명시하도록 누락도 보정했습니다. 새
Serial-only/include-only/SPI
clean/reuse build에서도 이 감사를 확인했습니다. M31 인접 Host 147건과 P0/builder Host 40건,
총 187건이 PASS했습니다. 전체 Host suite는 1,472건 PASS(2 skip)입니다. 55개 image의
fresh build·금지 symbol 0건·역할별 RAM 상한까지 완료해 P0를 닫았고, 다음은 P1의 pin/route와
GATT 고정 저장소 right-size입니다. 동적 high-water는 P2 경계로 남깁니다.
장치에는 접근하지 않았습니다.

## 1. 현재 상태

| 범위 | 상태·다음 작업 | 원본 |
| --- | --- | --- |
| 공개 설치본 | v0.4.1 단독 지원 | [릴리스 안내](<05_릴리스/v0.4.1/README.md>) |
| M28 / M29 / M30 | 각각 8/8 완료 | [v0.5.0 계획](TODO_v0.5.0.md), [M29 계약](<01_아두이노 코어 설계/16_M29_ATT_GATT_L2CAP_착수_계약.md>)·[readiness](../variants/nu54dk/m29-ble-readiness.json) (`M29-W01`), [M30 계약](<01_아두이노 코어 설계/17_M30_BLE_Security_Profile_DFU_착수_계약.md>)·[readiness](../variants/nu54dk/m30-ble-readiness.json) (`M30-W01`, `M30-POWER-01`) |
| M31-W01 | 원장·capability 완료 | [readiness](../variants/nu54dk/m31-ble-readiness.json) |
| M31-W02 | 설치본 ISO 11예제·11역할 완료 | [199번](<04_검증 기록/199_M31_W02_격리_설치본_ISO_11예제와_완료.md>) |
| M31-W03 | LE Audio 11/11 완료 | [214번](<04_검증 기록/214_M31_W03_LE_Audio_Profile_완료.md>) · [closure audit](<04_검증 기록/evidence/m31-w03-close-dc312cce/closure-audit.json>) |
| 메모리 최적화 | **P0 완료, P1 진행.** 55개 adaptive image gate를 완료했습니다. P1에서 pin별 transaction lease와 UART20 boot lease를 right-size해 SPI 정적 RAM을 50,877→24,613 B로 누적 26,264 B 줄였고 26,000 B 상한과 AC-02A target build를 고정했습니다. 다음은 SPI route 4,224 B와 GATT 저장소입니다. | [219번 계약](<04_검증 기록/219_M31_W06_메모리_점유_감사와_최적화_계약.md>) · [222번 P0 완료](<04_검증 기록/222_M31_메모리_최적화_P0_완료.md>) · [223번 P1 GPIO](<04_검증 기록/223_M31_메모리_최적화_P1_GPIO_상태_절감.md>) · [224번 P1 UART20](<04_검증 기록/224_M31_메모리_최적화_P1_UART20_lease_절감.md>) · [통합 설계 §5.0](<01_아두이노 코어 설계/21_M31_메모리_최적화_통합_설계.md#50-구현-진행-기록>) |
| M31-W04 DF | 미완료. connected RX 내부 진단 4 valid IQ report·328 sample, 전체 FAIL·raw IQ 안정성 HOLD | [216번 초기 경계](<04_검증 기록/216_M31_W04_연결_AoA_Controller_IQ_Event_진단.md>) · [220번 보존·인계](<04_검증 기록/220_M31_릴리스_전환과_문서_전수_정비.md>) |
| M31-W05 CS | 미완료. 같은 ACL 비암호화 read 거부 20/20, flash 직후 raw RAS 100·복구 20/20 두 번 PASS. wrong-key 실기·과거 중단 원인 잔여 | [217번](<04_검증 기록/217_M31_W05_비암호화_RAS_ATT_오류_진단.md>) · [218번](<04_검증 기록/218_M31_W05_flash_직후_RAS_복구_재검증.md>) |
| M31-W06~W08 | 미착수. 메모리 감사는 W06 기능 완료가 아님 | [M31 TODO](TODO_M31.md) |
| M32 / M33 | 0/12 · 0/8, 후속 버전 | [M32 TODO](TODO_M32.md) · [M33 TODO](TODO_M33.md) |
| Host | W01~W03 완료 3/8, W04~W08 보류 | [후속 다중 Host 계약](<02_빌드 설계/10_v0.5.0_다중_Host_지원_착수_계약.md>) |

M31은 **3/8 · not_completed**입니다. W03 완료나 일부 IQ 수신을 W04/W05/W06 완료로 확대하지
않습니다. 개발 결과는 v0.4.1 설치본 지원이나 v0.5.0 공개 완료가 아닙니다.

## 2. 고정 환경과 보존 이력

| 항목 | 값 |
| --- | --- |
| 이번 문서 정비 전 main | `8b20157d33f1d216620726d92d88f65c25491b4d` |
| 문서 정비 전 개발 HEAD | `51bfa1686c1a67b6d9f8f4e79c2623854b73dc11` (`m31-w04-dev`) |
| 이력 정리 전 main | `4dce513ee135512f66a36e936fde1baca2017115` |
| 7개 묶음으로 정리한 기준 | `ab0a54c536de560648b34dd7ec647ad6b774d149`와 그 뒤 이력 인계 문서 커밋; 현재 `origin/main` 확인 |
| 전체 원본 보존 태그 | `archive/main-before-milestone-squash-4dce513e` |
| 다음 개발 브랜치 | **`M31-MEM-OPT`**, 후속 작업에서 이력 정리된 main 기준으로 분기 |
| 최근 W04 raw IQ source | `22ff349c5996f8bb7b140fb427b744ecafe3d01c` |
| Target | nRF54L15 CPUAPP / `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| NCS | v3.4.0 / `99553055607b2e9885fbc80ccd11fa9da81c2df0` |
| Zephyr | `bf801e4e3d19e1ffa76164346480cb7734dd2800` |
| Board submodule | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| Windows toolchain | bundle `dcbdc366a1` |
| SDK lock | [ncs-3.4.0.lock.json](../tools/ci/ncs-3.4.0.lock.json) |
| SDK lock SHA-256 | `8c5ab4deaf0bb21dc83957330c49531d011e142959c6f93f7b47052bba5146f3` |
| 기존 squash commit | `d18309a1a9c64cbb4941efefb7189c8d99fcedf6` |
| Squash 전 원본 | `dac8ea8a85b8d2e1a84aa4299529a37e10f6c0f7` |
| 보존 태그 | `archive/m31-w03-before-squash-dac8ea8a` |

2026-09-21 후속 요청으로 공개 v0.4.1 마감 이후 189개 커밋을 7개 의미 단위로 정리하고
인계 기록을 별도 커밋했습니다. 기존 W03 squash 단위는 다른 내용과 합치지 않았지만
부모 이력 변경으로 새 SHA `96be7f3a0fecd0546b65794ddbe0c7448c58a5d5`를 갖습니다.
기존 SHA와 과거 source/image 증거는 원본 태그에서 그대로 조회합니다.
[215번](<04_검증 기록/215_M31_W03_이력과_문서_정비.md>)은 이전 이력 정리의 실행 기록이며,
[200번](<04_검증 기록/200_M31_다른_PC_작업_인계.md>)의 branch·COM mapping은 당시 snapshot입니다.
이전 릴리스 방향·문서 감사는 [220번](<04_검증 기록/220_M31_릴리스_전환과_문서_전수_정비.md>),
최신 이력 정리와 old/new 대응은 [221번](<04_검증 기록/221_main_마일스톤별_이력_정리.md>)을 따릅니다.

## 3. 다음 구현 순서

1. **메모리 최적화 P1부터** 진행합니다. P0에서 full profile의 API·capacity를 보존하고 lean role의
   미사용 feature/source를 제거했습니다. 이제 GATT·pin/route pool을 right-size합니다. final
   `.config`·ELF/map·절대 byte·headroom을 비교하고 stack/heap은 high-water 측정 뒤 조정합니다.
   [219번](<04_검증 기록/219_M31_W06_메모리_점유_감사와_최적화_계약.md>)의 측정·회귀 gate와
   [통합 설계](<01_아두이노 코어 설계/21_M31_메모리_최적화_통합_설계.md>)의 기능 선택·정정·구현 체크리스트가 기준입니다.
2. 최적화 image에서 **W04·W05 잔여와 변경 영향**을 닫습니다. 독립 코드·분석은 병행하되
   같은 probe나 보드를 동시에 점유하지 않습니다. 현재 실패/성공 원본을 보존합니다.
3. **W06**은 독립 role image별 RAM/RRAM·stack·buffer와 STOP/disconnect/restart 수명주기,
   공통 Core 변경의 M19~M30 회귀입니다. ISO·Audio·DF·CS 네 기능의 단일 MCU 동시 실행이
   아닙니다. Audio-over-ISO처럼 정의상 결합된 경로만 유지합니다.
4. **W07**에서 세 보드 역할 재배치와 설치 예제의 실제 실행을 검증합니다.
5. **W08**에서 readiness/API/예제/지원표/문서를 정합화하고 8/8 기능 마감을 판정합니다.
   Windows 패키지·clean 설치·예제·업로드·수명주기·RC·공개 승인 gate는
   [v0.5.0 TODO §6](TODO_v0.5.0.md#6-결과공개-규칙)에 따라 별도 판정합니다.

### W04 재개 시 놓치지 않을 실패 경계

원본 [connected-raw-iq.json](<04_검증 기록/evidence/m31-w04-connected-rx-22ff349c/connected-raw-iq.json>)에서
공개 Host API는 `-EINVAL`, 내부 HCI 두 명령은 수락, Host 상태 동기화 뒤 유효 report는
4건(각 82 sample)입니다. 최소 20 report와 cleanup을 충족하지 못해 **전체 FAIL**입니다.
반복 ANT_INFO/SCANNING/연결 시작과 최종 disconnect가 관찰됐으나 재시작 원인은 미확정입니다.
RX STOPPED·Host disarm 일부는 확인됐지만 TX STOPPED 등 양쪽 cleanup은 확인되지 않았습니다.

따라서 **다음 실기 전에 양쪽 STOP·clock 해제·GPIO 반환을 실제 확인**해야 합니다.
이번 문서 작업에서 보드 상태를 변경하거나 cleanup 성공을 추정하지 않습니다.
Connected와 connectionless RX, controller별 source/build/HCI/IQ report, 공개 API와 내부 진단을
분리합니다. SDC AoD 미지원·안테나 전환·각도 계산·외장 RF를 raw IQ와 합치지 않습니다.

### W05 재개 시 남은 항목

동일 ACL read 거부와 flash 직후 두 번의 성공을 과거 간헐 중단의 단일 원인 확정으로 쓰지
않습니다. wrong-key runner/fixture는 준비됐지만 실기는 **NOT RUN**입니다. 정상 bond 후
reflector bond만 공개 `eraseAllBonds()`로 지우고 repair pairing을 거부하는 one-sided stale-key
negative가 최소 범위이며, 서로 다른 LTK 직접 주입 시험으로 확대하지 않습니다.
비보정 RTT 출력은 정밀 거리 정확도 PASS가 아닙니다.

## 4. 다른 PC에서 재개하기

1. 실제 저장소의 [AGENTS.md](../AGENTS.md)를 읽고 branch·HEAD·미커밋 변경을 확인합니다.
   `git fetch origin --tags` 후 현재 `origin/main`과 원본 보존 태그를 대조합니다.
   이번 main은 비-fast-forward로 재작성됐으므로 이전 checkout을 무작정 pull/merge하지 않습니다.
   로컬 변경·독자 커밋을 먼저 보존하고 새 main 기준 checkout에서 후속 브랜치를 만듭니다.
   Dirty/diverged 상태를 reset으로 덮어쓰거나 오래된 이력을 main에 다시 merge하지 않습니다.
2. 위 SDK lock hash·NCS/Zephyr/toolchain·board gitlink를 직접 대조합니다. 현재 장치나
   임시 HEX가 이전 PC와 같다고 가정하지 않습니다.
3. 보드 시험 직전 exact probe UID의 SHA-256 identity·COM·role·image hash를 다시 결합합니다.
   원시 UID는 공개하지 않습니다. 배타 probe lock·watchdog·lease·STOP을 유지합니다.
4. 자동 mass erase/unlock/recover, 임의 결선·전원·USB 변경은 금지합니다. 필요한 물리 변경은
   먼저 사용자에게 요청합니다. 실패는 UART/HCI/레지스터·exact image/source로 진단합니다.
5. 공개 `.ino`에는 읽고 수정 가능한 C++/NUCODE payload·오류·종료 흐름을 둡니다.
   Zephyr 직접 호출·M31/시험 ID/HIL protocol은 공개 API·예제·출력에 노출하지 않습니다.

## 5. 검증·공개 경계

- W02/W03 완료와 M30 실제 전원 차단 12/12의 기존 source·조건은 보존합니다.
  최적화의 영향 재검증이 필요해도 과거 PASS/FAIL 원본을 소급 변경하지 않습니다.
- 외장 PDM/I2S·mic/speaker/codec·상용 peer 실물은 사용자 후속 **NOT RUN**·비차단입니다.
  채택 기능의 구현·예제·가능한 자동 검사 의무를 면제하는 규칙은 아닙니다.
- Ubuntu/macOS의 `final_release`·`release_blocker=true`는 해당 OS를 지원할 후속 릴리스
  gate입니다. v0.5.0 Windows 범위로 지원되지 않은 OS를 PASS 처리하지 않습니다.
- 정밀 RF·음질·거리/각도 보정·qualification은 보드 기능 PASS에 포함하지 않습니다.
- CI/CD 실행 요청·상태 조회·대기는 사용자 지시로 생략합니다. 이번에는 로컬 문서·계약
  검사만 수행하며 firmware build·물리 HIL은 **NOT RUN**입니다.
