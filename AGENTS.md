# 저장소 작업 안내

## 시작 전에

1. [v0.4.1 유지보수 TODO](00_Docs/TODO_v0.4.1.md)와 [v0.4.0 완료 TODO](00_Docs/TODO_v0.4.0.md)를 전체 읽고, 작업에 해당하는 계약·검증 기록을 확인합니다.
   M28 이후 작업은 [v0.5.0 착수 계획](00_Docs/TODO_v0.5.0.md)도 읽고, 준비 체크와 구현·실기 상태를 구분합니다.
2. R00~R14 리팩토링 관련 변경은 [리팩토링 안내](<00_Docs/01_아두이노 코어 설계/14_리팩토링/README.md>)와
   [진행 체크리스트](<00_Docs/01_아두이노 코어 설계/14_리팩토링/05_리팩토링_진행_체크리스트.md>)도 읽습니다.
3. 실제 저장소·branch·HEAD·미커밋 변경·board submodule을 확인하고 기존 사용자 변경을 보존합니다.
4. 최신 사용자 요청이 과거 작업 일지보다 우선합니다. TODO는 flash·결선 변경·공개·삭제의 포괄적 허가가 아닙니다.
5. 구현 전 해당 T/M/R 항목 또는 공개 후 유지보수 범위를 기록하고, 종료 시 결과·검사·증거 링크를 갱신합니다.

## 현재 완료 상태와 지원 경계

- **v0.4.0의 T01~T25와 R00~R14는 완료됐습니다.** 공개·T24 설치 수명주기·T25 마감은
  [125번 기록](<00_Docs/04_검증 기록/125_v0.4.0_정식_릴리스_공개와_T24_T25_마감.md>)을 따릅니다.
  과거의 “U 진행 중”, “다음 T22 승인”을 현재 작업으로 재개하지 않습니다.
- **현재 설치·지원 대상은 v0.4.1 하나입니다.** 이전 stable·RC·preview는 지원·stable catalog
  공급을 종료하며, 과거 tag·Release·자산·검증 기록은 삭제하거나 소급 수정하지 않습니다.
- **개발 브랜치의 M28·M29·M30은 완료했습니다.** M30은 W01~W08 8/8, test ID 10/10,
  M30-W08 실제 전원 차단 4지점 × 3회(12/12)를 통과했습니다. HOST-W01~HOST-W03은 완료했고
  HOST-W04~HOST-W08은 사용자 지시로 보류 중입니다. M31은 W01~W08 **8/8 완료**이며,
  W03 LE Audio는 **11/11**입니다. W04 DF·W05 CS·W06 자원/영향 회귀·W07 설치 예제 49/49와
  3보드 역할 HIL·W08 Windows RC 준비를 완료했습니다. 현재 branch는 `0.5.0-RC1`이며 다음은
  별도 v0.5.0 공개 승인입니다.
  2026-09-21 후속 요청으로 main의 미공개 개발 이력을 정리했습니다. 원본 보존·
  새 SHA 대응은 [221번 기록](<00_Docs/04_검증 기록/221_main_마일스톤별_이력_정리.md>)을 따릅니다.
  이번 이력 정리는 구현·실기 재개나 새 릴리스 공개가 아닙니다.
  기능 판정 원본은 [M31 readiness](variants/nu54dk/m31-ble-readiness.json)입니다.
  개발 기능을 v0.4.1 설치본의 지원으로 안내하지 않습니다. 재개 지점은 [HANDOFF](00_Docs/HANDOFF.md),
  후속 순서·중단 경계는 [v0.5.0 TODO](00_Docs/TODO_v0.5.0.md)와 최신 사용자 요청을 따릅니다.
- M31~M33 구현 전에는 [전체 Bluetooth 기능·예제 계약](<00_Docs/01_아두이노 코어 설계/19_NCS_Bluetooth_전체_기능과_예제_실행_계약.md>)과
  해당 [M31](00_Docs/TODO_M31.md)·[M32](00_Docs/TODO_M32.md)·[M33](00_Docs/TODO_M33.md) TODO를 읽습니다.
  계획 분모는 8·12·8이고 문서 개정은 구현 완료가 아닙니다. 2026-09-16 사용자 결정에 따라 보드 기반
  기능 HIL과 NCS 예제의 Arduino 제공을 목표로 하며 정밀 RF·음질·거리/각도 보정은 필수 gate 밖입니다.
  Apple/Google 등 외부 peer와 마이크·스피커·외장 장치는 사용 가능한 구현·예제·설정/연결 안내·자동
  가능한 검사를 제공하되, 실제 운용·실물 검증은 사용자 후속입니다. 그 NOT RUN은 v0.5.0 개발·공개
  차단 조건이 아니며 검증된 상호운용으로 표시하지 않습니다. M32/M33 기능은 후속 버전(미정)이며
  v0.5.0 범위에 합산하지 않습니다. Ubuntu/macOS 실물 Host 검증은 해당 OS를 지원하는 후속 릴리스의
  사용자 gate이며 v0.5.0 Windows 릴리스의 선행조건이 아닙니다. ARF-01은 M32-W04가 소유합니다.
- **2026-09-21 결정: v0.5.0은 완료한 M31을 기준으로 Windows 10/11 x64 범위로 릴리스합니다.**
  M31 8/8 기능 완료와 패키지·clean 설치·예제·업로드·수명주기·RC·공개 승인 gate를 별도로 판정합니다.
  M31-W08이 배포 준비를 소유하며 M32/M33·다중 Host 확장 완료를 기다리지 않습니다.
  일반 문서·main 업데이트 허가는 release/tag 공개나 이력 squash 허가가 아닙니다.
  이번 squash는 별도 사용자 요청에 따른 221번 한정 작업이며 향후 반복 허가가 아닙니다.
- **P2 세 기술 축은 완료**했다: 지원 범위 오류·최악 부하, stack/heap 안전 여유·최종 크기,
  동등 조건 Nordic native FLASH/RAM 비용 비교. W06도 독립 image 자원·수명주기와 M19~M30
  영향 회귀를 완료했고 W07도 설치 예제와 3보드 역할 HIL을 완료했다. 세부 근거는
  [M31 TODO](00_Docs/TODO_M31.md#p2-완료--세-축)를 따른다.
- **NCS v3.4.0·제품 SDC를 유지한다.** nRF54L15 제품 DF IQ RX·AoD는 공식 고정 SDK 근거로
  `UNSUPPORTED`이며 IQ RX를 P2 필수 gate로 되살리지 않는다. [259번](<00_Docs/04_검증 기록/259_M31_P2_DF_고정_SDK_지원_경계.md>)을
  따른다. Zephyr LL 연결형 내부 IQ 성공과 connectionless 실패·fault는 역사 증거로 보존하며
  제품 수신 PASS나 SDK/controller 변경 허가로 확대하지 않는다.
- CS 간헐 RF/controller loss·counter gap은 관찰값이며 P2 합격 조건에서 제외한다.
  유효 raw·step·완료 수·STOP·fault·중복/역행 검사는 유지한다. SDC 내부 high-water 비노출도
  추가 gate가 아니다. SDK 역할/count별 요구량과 8-byte 정렬을 준수하고 근거 없는 pool 축소를 금지한다.
  물리 전원 차단·임의 다중 link·모든 조합을 새 필수 과제로 추가하지 않는다.
- T13 S는 **56 PASS + 2조건 제외 / 58**, UARTE00은 4-net 결선 검사·180초 통신·flow 200회·취소 400회 완료입니다.
  완료한 S/U, C05 1시간 soak와 사용자 제외 항목을 새 요청 없이 다시 예약하지 않습니다.
- **QDEC20/21은 공개 지원**합니다. 기본 정·역회전과 SAMPLE/REPORT event 경로가 근거이며,
  반복 manual `read()/clear`의 무손실 누산은 보증하지 않습니다. [124번 지원 계약](<00_Docs/04_검증 기록/124_T22전_QDEC_지원_범위_재확정.md>)을 따릅니다.
- 반복 Serial personality handover, 모든 주변장치 동시 조합, 정밀 ADC 정확도·jitter·음질·신호 무결성은 보증 범위 밖입니다.
- 과거 GPIO/SWD 진단, I2S 결선 오류, 별도 SPI early-CS 판정과 TWIS read-request 지연 요구는
  현재 결함·잔여 작업 표에 다시 넣지 않습니다. 원본 시험 기록은 보존합니다.
- 해결된 문제에는 **해결 완료**를 명시합니다. 검증 미실행·범위 제외·알려진 제한은 확정 결함과 구분합니다.

## 검증·문서 원칙

- Host·mock·build 통과나 범위 결정은 물리 PASS가 아닙니다. source·image·조건·결과를 결합해 기록합니다.
- 공개 자산과 과거 PASS/FAIL/HOLD/NOT RUN 원본을 보존합니다. 생성 문서는 JSON·생성기를 고쳐 재생성합니다.
- SDK·third-party·board submodule은 임의 수정하지 않습니다. 문서 경로 변경 시 들어오는 링크도 함께 고칩니다.
- 2026-09-08 소유자 승인 이력 정리·v0.3.0 미만 공급 종료는 완료된 예외입니다. 반복 실행 허가가 아닙니다.
  원본 보관은 [106번 기록](<00_Docs/04_검증 기록/106_Git_이력_정리와_구버전_패키지_공급_종료.md>)을 따릅니다.
- TODO는 완료 상태와 증거를 찾는 진입점으로 보관합니다. 삭제·이관은 문서의 보관 조건을 따릅니다.
- 진행 보고에는 완료 범위·현재 항목·남은 항목·진행률을 적습니다. 문서 정비 진행률과 S 실기 분모 58을 혼합하지 않습니다.
- 커밋·푸시를 수행했다면 해당 exact SHA의 CI 결과를 확인하되, 최신 사용자의 명시적 생략 지시가
  있으면 따릅니다. M31-W08은 승인된 GitHub Actions Windows shard와 로컬 HIL 증거를 사용합니다.
  생략·실행 중인 검사를 성공으로 기록하지 않습니다.

## 실물 보드 작업을 새로 요청받았을 때

- 현재 연결 상태를 과거 문서에서 추정하지 않습니다. 해당 fixture의 GPIO 연결성을 먼저 확인합니다.
  S는 17신호, U는 연결된 UART00 4신호만 검사합니다.
- 사용자가 유지한다고 확인한 결선에 임의 시간 만료를 붙이지 않습니다. 새 오류가 생기면 GPIO 연결성부터
  확인하고, nRF54L15의 CMSIS-DAP으로 GPIO·주변장치·DMA·IRQ·오류 상태를 확보해 진단합니다.
- 원인 규명 → 근거 있는 수정 → 동일 조건 재검증 순서를 지킵니다. 이유 없는 무한 재시도는 하지 않습니다.
- Firmware watchdog·명령 lease·STOP/핀 반환·배타 probe lock은 유지합니다.
  양쪽 STOP·clock 해제·GPIO 반환이 확인되지 않으면 후속 시험을 시작하지 않습니다.
- Exact UID/image·sector flash·`auto_unlock=false`를 사용합니다. 자동 mass erase·unlock·recover는 하지 않습니다.
  물리 배선·전원·USB 변화는 실제 상태와 대조하고, 원시 UID·인증 정보는 공개 문서에 넣지 않습니다.

## First-party C/C++ 스타일

한국어 Doxygen 주석, BSD/Allman 중괄호, 들여쓰기와 탭 폭 4칸을 사용합니다.
제어문 본문은 한 줄이어도 중괄호를 생략하지 않습니다.
[.clang-format](.clang-format)과 [정렬 도구 안내](tools/format/README.md)를 따릅니다.

## 공개 Arduino 예제와 backend 경계

- 공개 `.ino`에는 일반 C/C++과 해당 library의 `NUCODE_*` 공개 API를 사용한 의미 있는
  `setup()`/`loop()` 흐름을 둡니다. 구현 전체를 헤더 하나에 숨긴 include-only sketch는 금지합니다.
- 데이터 송수신 예제는 사용자가 payload 생성·전송과 수신 데이터 처리·오류·종료 흐름을 `.ino`에서
  읽고 바꿀 수 있어야 합니다. `begin()`/`poll()`만 호출하고 고정 시험 payload·세션을 library
  내부에서 실행하는 sketch는 공개 예제 완료로 세지 않습니다.
- 공개 `.ino`에서 Zephyr header·type과 `bt_*`, `k_*`, `device_*` API를 직접 호출하지 않습니다.
  Zephyr/NCS 직접 구현은 library `.cpp` 또는 `src/internal`이 소유합니다.
- `M31`, `M32` 같은 개발 마일스톤 식별자를 공개 API, class, macro, 예제, 광고 이름과 사용자
  출력에 넣지 않습니다. 시험 ID와 증거 protocol은 `tests`와 검증 도구 내부에만 둡니다.
- 역할·기능 선택은 공개 enum/config와 검증된 Kconfig feature로 표현합니다. Sketch-local 개발용
  `#define`으로 backend 역할을 고르지 않습니다.
- 예제 변경은 `tools/ci/m31_example_audit.py`의 공개 경계 검사와 해당 예제 build를 통과해야 합니다.
- HIL UART oracle·nonce·고정 count·마일스톤 출력은 `tests`의 전용 시험 image에만 둡니다.
  공개 library에서 시험 backend를 재사용할 때는 사용자 데이터 API와 출력 경계를 별도로 검증합니다.
