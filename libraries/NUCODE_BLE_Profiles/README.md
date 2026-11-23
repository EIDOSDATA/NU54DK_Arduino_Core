# NUCODE BLE Profiles

사용자 값은 `.ino`에서 만들고, 이 라이브러리는 표준 characteristic wire 형식과 기존
NUCODE BLE의 generation별 GATT 경계에 연결합니다. Bluetooth SIG 인증, 모든 선택 기능,
Apple/Google peer 상호운용 또는 의료기기 적합성을 주장하지 않습니다.

## 어디서 시작할까

처음에는 **StandardSensor + StandardCollector** 두 예제를 봅니다. 두 파일의 `sensorKind`만
같이 바꾸면 HTS, CTS, CSC, RSCS, ETS를 같은 연결·구독 흐름으로 배웁니다. 특정 기능이
필요할 때 아래 확장 예제를 선택합니다. 기존 예제를 삭제하거나 같은 의미의 예제로
취급하지 않고, 공통 흐름을 한 진입점에 모았습니다.

| 목적 | 예제 | 구현 범위 |
|---|---|---|
| 온도·시간·운동 측정 | StandardSensor / StandardCollector | CTS read/notify, HTS indicate, CSC crank-only, RSCS speed/cadence/stride/running, ETS read/indicate |
| 알림 category 허가 | AlertSensor / StandardCollector | ANS New/Unread, 10 category, link별 enable/disable/immediate |
| 연속 혈당 모의 데이터 | GlucoseSensor / StandardCollector | NCS CGMS record·주기 notify 및 아래 native 제약 |
| 요청 peer의 bond 삭제 | BondManagement | BMS LE requesting-peer opcode 03, 암호화·bond·일회 무장·사용자 코드 필수 |
| RAM object 전송 | ObjectServer / ObjectClient | OTS/OTC discover, first/next/goto, metadata, CoC read/write, create/name/delete |

공개 예제는 총 7개입니다. StandardSensor/Collector는 서비스별로 같은 코드를 복제하지
않으며, 각 서비스의 typed 값·단위·인코딩은 해당 switch 안에 보입니다. 모든 예제는
Arduino API만 사용합니다. Zephyr 호출은 library backend에 있습니다.

## 사용 계약과 범위

- `SensorService`, `AlertService`, `BondManagementService` 객체는 static/global 수명으로
  두고 `begin()`을 `BLEDevice.begin()` 전에 호출합니다. 정상 loop에서는
  `BLEDevice.poll()`과 필요한 `BLESecurity.poll()`/`AlertService.poll()`을 호출합니다.
- CTS는 자연 시간 경과를 자동 통지하지 않습니다. 앱이 실제 조정을 표현하는 값을
  넣고 전송 정책을 결정합니다. writable clock·Local Time Information 등 선택 기능은
  광고하지 않습니다.
- CSC service feature는 crank만 광고합니다. portable codec은 wheel 형식도 해석하지만,
  service의 `setValue()`는 wheel 값을 거부합니다. RSCS service는 total distance를
  광고하거나 수락하지 않습니다. 누적 거리 codec 단위는 0.1 m입니다.
- HTS FLOAT는 signed 24-bit mantissa와 exponent, CGMS SFLOAT는 signed 12-bit mantissa와
  exponent입니다. 특수 NaN/무한대 raw 표현을 정상 생체 측정값으로 해석하지 마세요.
- ANS 제어 상태는 최대 2개의 정확한 connection generation별로 보관합니다. disconnect
  후 이전 category 허가는 재사용되지 않습니다. UTF-8 문구는 최대 18 octet이며 RFU,
  손상된 UTF-8, 잘린 packet과 불필요한 trailing byte는 거부합니다.
- BMS는 암호화된 bonded 요청자 한 peer만 삭제합니다. `setArmed(true)`는 다음 승인된
  한 건에 소비되며 기본은 미무장입니다. authorization callback은 Bluetooth 문맥이므로
  짧고 non-blocking이어야 합니다. 예제의 데모 문구는 비밀 인증수단이 아닙니다.
  전체 bond 삭제는 지원하지 않습니다. 영속 삭제 확인은 재부팅/재연결 실험이 필요합니다.
- generic ANS/BMS authorization 거부는 ATT authorization error를 사용합니다.
  서비스별 모든 application error code의 SIG 적합성을 주장하지 않습니다.

## NCS 3.4.0 native adapter

`GlucoseSensor`, `ObjectServer`, `ObjectClient`는 동봉된 `prj.conf`가 필요합니다.
이 구성에서 `CONFIG_BT_MAX_CONN=1`을 요구하며 2-link 구성의 `begin()`은
`false`/`-ENOTSUP`로 실패합니다. native SDK의 단일 session/현재 object 상태를
두 peer에게 공유하지 않기 위한 명시적 제한입니다. SDK를 바꾸지 않습니다.
OTS/OTC의 `CONFIG_BT_OTS_OBJ_MAX_NAME_LEN`은 정확히 32이어야 합니다. 다른 값은
compile-time에 거부하여 SDK rename과 facade 고정 buffer 크기가 달라지지 않게 합니다.

### CGMS

`GlucoseService`는 `bt_cgms_init()`으로 session을 시작하고 실제 native record 저장소에
사용자 SFLOAT 값을 넣습니다. 기본 주기는 1분이며 공개 예제는 인증 시간을 포함해 185초 실행합니다.
이 예제는 synthetic 데이터이며 센서나 의료 측정값이 아닙니다.
고정 SDK의 measurement CCC와 control point는 authenticated(L3) 권한이 필요합니다.
`GlucoseSensor`와 `StandardCollector(Kind::glucose)`의 양쪽 Serial Monitor를 열고
표시된 6자리 숫자가 실제로 일치할 때만 30초 안에 각각 `y`를 입력합니다. `n`은 거부합니다.
자동 numeric comparison 승인이나 고정 passkey는 공개 예제에 사용하지 않습니다.
이전 bond는 보존하며, 인증 실패를 성공적인 구독으로 표시하지 않습니다.

고정 SDK에서 확인한 실제 범위:

- SOCP 통신주기 read `02`와 write `01 <minutes>`를 지원합니다.
- SOCP start `1a`와 stop `1b`는 명시적인 unsupported response입니다.
- RACP report records `01`, report number `04`, abort `03`을 처리합니다.
  RACP delete `02`는 unsupported response입니다.
- record 16개가 차면 오래된 record를 교체합니다. session 시간 만료 뒤 add는 실패합니다.
- `BLEDevice.end()`는 radio/연결을 종료하지만 native CGMS session timer/주기 작업을
  즉시 취소하는 API는 이 adapter에서 제공하지 않습니다. 재초기화는 reset 경계입니다.

근거는 NCS 3.4.0의 `nrf/subsys/bluetooth/services/cgms/cgms.c`, `cgms_socp.c`,
`cgms_racp.c`입니다. 이는 관찰한 지원 범위이며 시험 실패의 원인을 미리 SDK로
단정하는 설명이 아닙니다.

### OTS / OTC

- RAM object 최대 4개, object당 512 byte, 이름 32 octet입니다. 재부팅하면 사라집니다.
- local add/remove는 미연결 상태에서만 허용합니다. 이름·ID·offset·capacity 경계를
  검사하며 SDK가 반환한 48-bit ID를 정확히 매핑합니다. ID 나머지 연산으로 slot을
  재사용하지 않습니다. 중복 이름은 거부합니다.
- remote read/write/create/name/delete는 암호화된 link가 필요합니다. SDK delete callback이
  connection을 전달하지 않는 경로도 있으므로 OTS UUID 범위의 ATT read/write를
  global authorization callback으로 보호합니다. 다른 global callback이 이미 등록된
  경우 `begin()`이 실패하며 이를 대체하지 않습니다. 다른 서비스의 접근 정책은
  이 callback에서 변경하지 않습니다.
- 요청과 응답은 하나씩 처리합니다. `poll()`의 10초 deadline이 지나면 오류 이벤트를
  내고 연결 종료를 요청합니다. write payload는 고정 내부 buffer에 복사합니다.
  create/delete의 ATT 응답과 OACP indication 순서가 바뀌어도 둘 다 완료되기 전에는
  다음 요청을 허용하지 않습니다.
- 완료 read callback 직후 이전 CoC가 비동기로 해제되는 동안 다음 read/write가
  `-ENOMEM`을 반환할 수 있습니다. 이 **완료 read 이후 최대 10초 창**에서만 요청을
  내부 보관하고 `poll()`이 10ms 이상 간격으로 다시 제출합니다. 일반 ENOMEM·다른
  오류는 자동 재시도하지 않습니다. 대기 중 `busy()`는 true이고 payload는 복사됩니다.
  deadline·cancel·disconnect에서 대기를 해제하며 timeout은 연결 종료를 요청합니다.
  NCS 3.4.0 OTC public API는 별도 CoC closed callback을 노출하지 않습니다.
- SDK client와 L2CAP context는 image lifetime에 한 번만 등록하며 disconnect 뒤에는
  같은 public client 객체의 handle을 재발견합니다. 고정 SDK unregister/register를
  반복하여 내부 L2CAP list node를 다시 연결하지 않습니다. metadata 완료 시 size/capacity를
  facade 소유 snapshot에 복사하고, 비동기 metadata 중 read/write는 busy로 거부합니다.
- OACP/OLCP indication 구독은 `VOLATILE`이며 bond 유무와 관계없이 연결 종료 때
  제거합니다. 다음 `begin()`은 재발견·새 CCC 구독을 수행합니다. 고정 Zephyr의
  `host/gatt.c` `remove_subscriptions()`가 유지하는 비휘발 intrusive node를
  초기화하지 않도록 한 adapter 수명 계약이며, 자동 재구독에 의존하지 않습니다.
- 읽기/쓰기 전에 metadata를 읽습니다. `c` 생성 다음에는 `t`로 이름을 설정합니다.
  이름 없는 새 object는 SDK가 disconnect 시 폐기합니다. 원하는 새 길이로 truncate하는
  API는 제공하지 않으며 현재 write는 bounded patch/write입니다.
- 선택 기능인 checksum, directory listing, timestamp, append/truncate, object execute는
  이 facade의 지원 범위가 아닙니다. 큐는 8 event이며 넘치면 `lastError()=-ENOBUFS`입니다.

근거는 NCS 3.4.0의 `zephyr/include/zephyr/bluetooth/services/ots.h`와
`zephyr/subsys/bluetooth/services/ots/`입니다. SDK의 OTS/OTC experimental 표시는
그대로 적용합니다.

## 검증과 남은 확인

Host 검사는 `tests/host/test_m33_profile_codec.py`, `test_m33_profile_runtime.py`,
`test_m33_profile_native.py`, `test_m33_profile_hil.py`입니다. 실제 production codec,
generic GATT backend, native adapter 코드를 컴파일하며 native 호출 경계만 시험 대역을
사용합니다. 이것은 무선 HIL이나 외부 peer 인증을 대신하지 않습니다.

`tests/zephyr/m33_profile_hil`과 `tests/hil/nu54dk/m33_profile_run.py`는 별도 개발 HIL입니다.
standard 세 역할은 CTS/HTS/CSC/RSCS/ETS payload, ANS malformed 및 두 link category 격리,
BMS 금지 opcode·미무장 거부와 새로 만든 requester bond만의 scoped 삭제를 검사합니다.
기존 bond 소유 여부를 증명하지 못하면 positive 삭제는 NOT_RUN입니다. native 두 역할은
OTS round-trip·객체 관리·CGMS 두 주기 수신·지원/미지원 control 응답과 정상/partial CoC
취소 후 재연결을 구분합니다. 사용하지 않는 세 번째 보드도 known idle image로 격리합니다.

실제 실행 결과가 등록되기 전에는 이 HIL을 NOT_RUN으로 취급합니다. BMS 영속 삭제
재부팅 지속성, native 두 번째 peer 실물 거부와 장시간 재연결 soak, Apple/Google
peer·외부 센서 시험은 별도 분모입니다. 기존 M30 7개 profile evidence를 새 9개 서비스의
검증으로 전용하지 않습니다. Target build·image hash·RAM과 실물 결과는 통합 evidence가
최종 기준입니다.

Wire 형식의 기준은 [Bluetooth SIG GATT Specification Supplement](https://btprodspecificationrefs.blob.core.windows.net/gatt-specification-supplement/GATT_Specification_Supplement.pdf),
[Assigned Numbers](https://www.bluetooth.com/wp-content/uploads/Files/Specification/HTML/Assigned_Numbers/out/en/index-en.html),
[Elapsed Time Service 1.0](https://www.bluetooth.com/wp-content/uploads/Files/Specification/HTML/ETS_v1.0/out/en/index-en.html)입니다.
