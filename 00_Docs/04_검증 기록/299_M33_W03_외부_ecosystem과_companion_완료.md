# M33-W03 외부 ecosystem과 companion 완료

## 1. 판정

M33-W03은 기능 source `17182660f8c1c1f4a9f6773b13fcfa453f65e1fc`에서 **완료**다.
NCS v3.4.0과 board submodule `fe65f2f…`를 유지했고, 공개 Apple client 2개, 독립 native
template 4개, Host negative 13개와 실제 NU54DK 두 보드 scripted-peer HIL 9개를 검사했다.

이 완료는 실제 Apple/Google 제품, EnOcean 장치, Memfault cloud/gateway, 외부 Auracast receiver의
상호운용 PASS가 아니다. 해당 행은 사용자 후속 `NOT_RUN`이고 개발·릴리스 비차단이다. AuraConfig
원본의 nRF5340 Audio DK 전용 route는 NU54DK에 `NOT_APPLICABLE`로 남겼다.

## 2. 구현 결과

### 2.1 Apple ANCS·AMS

- `NUCODE_BLE_Companion` 공개 API에 advertising, 보안 연결, service/attribute/CCC discovery,
  ANCS notification·분할 attribute·action과 AMS supported command·entity update·long read·control을 구현했다.
- `AppleNotificationClient`, `AppleMediaClient` 예제는 공개 C++ API만 사용하고 Zephyr API를 노출하지 않는다.
- 요청 단일화, 15초 session/5초 request timeout, 길이·UID·attribute·truncated 검증, stale session 차단,
  malformed fail-closed, disconnect/reconnect와 bond 복원 경계를 구현했다.
- Core를 거치지 않은 legacy advertising도 내부 GAP 수명주기에 등록해 incoming connection이
  잘못 거부되지 않게 했다. 기존 초기화된 BLE stack은 중복 초기화하지 않는다.

### 2.2 Fast Pair·EnOcean·MDS template

- Fast Pair input과 locator는 고정 SDK의 전체 application source를 새 output으로 복제하고
  NU54DK loaderless layout, board overlay와 credential 입력을 적용한다.
- model/use case/environment/key 형식, placeholder, 잘못된 P-256 scalar와 명령 주입을 fail-closed로
  거부한다. 시험 credential에는 명시적인 opt-in을 요구하고 실제 비밀은 저장소 밖에 둔다.
- EnOcean과 MDS도 빈 성공 stub가 아니라 고정 SDK 원본을 실제 NU54DK target으로 build한다.
  MDS key/device ID를 외부 입력으로 제한하고 EnOcean commissioning·Memfault cloud 실기는 후속으로 분리한다.
- 생성기는 기존 output을 덮어쓰거나 flash·erase·recover하지 않는다. Fast Pair application HEX와
  provisioning HEX는 분리해 기록하며 자동 병합·기록하지 않는다.
- nRF AuraConfig 원본은 고정 sample metadata와 README가 nRF5340 Audio DK만 허용하므로 NU54DK
  native 제공을 주장하지 않는다. 기존 Public Audio 예제의 적용 범위와 차이도 사용자 안내에 명시했다.

## 3. exact 검증

| 항목 | 결과 |
| --- | --- |
| Host codec/security/reset/template/runner negative | 13/13 PASS |
| AppleNotificationClient / AppleMediaClient Arduino build | 2/2 PASS |
| Fast Pair input / locator native template build | 2/2 PASS |
| EnOcean / MDS native template build | 2/2 PASS |
| Scripted peer HIL case | 9/9 PASS |
| 시험 소유 bond cleanup | client 1/1, peer 1/1 PASS; 기존 bond 불변 |

문서·readiness 갱신 뒤 전체 `test_m33*.py` 57/57, readiness·예제 안내 17/17과 Markdown
UTF-8/local-link 489개를 추가 PASS했다.

HIL은 access 거부 1개와 2회 cycle의 ANCS·AMS 정상/비정상 세션 8개를 수행했다. Fresh pairing,
bonded reconnect, notification/attribute/control, stale nonce, malformed command, remote pairing rejection,
명시적 client-ready/peer-release handshake와 유한 STOP을 검사했다. 일시적 HCI `0x3e` 연결 실패는
무제한 재시도가 아니라 scan/link가 모두 없는 상태에서만 bounded retry하도록 했고, 최종 분모와
허용 실패 0은 바꾸지 않았다.

실기 전 디버거로 세 보드의 DP/AP·nRF54L15 FICR·M33 CPUID·APPROTECT를 대조했다. Client와 peer는
500 kHz sector write, `auto_unlock=false`, no-reset 뒤 exact readback과 cooperative software reset으로
실행했다. 격리한 세 번째 보드는 HALTED, RADIO state 0, 활성 DPPI route 0을 확인했고 프로그램·reset·
resume하지 않았다. 자동 mass erase·unlock·recover는 실행하지 않았다.

상세 manifest·HIL result·transcript·비식별 preflight는
[`m33-w03-exact-17182660`](<evidence/m33-w03-exact-17182660>)에 있다. 원격 CI는 조회하거나 기다리지 않았다.

## 4. `M33-ECOSYSTEM-01` 분리

Readiness는 한 개의 포괄 PASS 대신 다음 7개 필수 개발 case를 독립 PASS로 기록한다.

1. Fast Pair input template build와 credential negative
2. Fast Pair locator template build와 use-case 분리
3. ANCS fresh/reconnect/malformed scripted-peer session
4. AMS reconnect/control/malformed scripted-peer session
5. 명시적 pairing/access 거부
6. EnOcean·MDS native template build
7. Apple/Google/일반 OS UX 지원표와 `NOT_RUN` 승격 거부

실제 Apple ANCS/AMS, Google Fast Pair input, Google Find Hub locator, EnOcean 제품, Memfault gateway/cloud는
별도 follow-up case다. 자동 결과를 이 행들로 복사하지 않는다.

## 5. 남은 범위와 다음 작업

- 실제 Apple/Google peer·외장 장치 실기는 사용자 후속이며 실행 전 장비·계정·credential·수동 승인
  가능 여부를 확인한다. 미실행을 PASS로 처리하지 않는다.
- NCS 3.4.1의 Fast Pair/DULT 변경은 v0.7.0 SDK 전환에서 재검증한다. 현재 3.4.0 시험 실패의
  원인으로 단정하지 않는다.
- M33 다음 작업은 W04 DTM/HCI다. W04~W06을 마친 뒤에만 HOST-W04를 시작한다.
