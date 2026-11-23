# M33-W02 Beacon 코덱과 예제 착수 검증

## 1. 판정 범위

`Dev-0.6.0-M33`의 exact 구현 후보
`5f79ba69da503006fbcabdc2493f5146c22d3f63`에서 iBeacon, Eddystone UID,
BTHome v2의 portable payload 코덱과 공개 advertiser/observer 예제를 검사했다. 이 기록은
Host 코덱과 Arduino build에 한정한 **부분 PASS**다. `M33-BEACON-01:formats`의 2보드
600 advertisement HIL과 M33-W02의 표준 GATT profile은 아직 `NOT_RUN`/미완료다.

## 2. 구현 결과

- `NUCODE_BLE_Beacon`은 heap과 Zephyr 내부 API 없이 다음 고정 형식을 encode/decode한다.
  - iBeacon: Apple company ID `0x004c`, type `0x02`, length `0x15`, UUID 16 byte,
    big-endian major/minor, signed measured power.
  - Eddystone UID: UUID `0xfeaa`, frame type `0x00`, 0 m TX power, namespace 10 byte,
    instance 6 byte, RFU `0x0000`.
  - BTHome v2: UUID `0xfcd2`, 비암호화 device-info, packet ID, little-endian signed
    temperature `0x02`, humidity `0x03`과 오름차순 object ID.
- 전체 AD structure의 length/type/16-bit identifier를 끝까지 검사한다. 잘린 field, 잘못된
  company/UUID/frame/version, 암호화 bit, 예약 bit, RFU, TX power와 습도 범위를 거부한다.
- 공개 예제는 protocol별 6개로 나누지 않고 `BeaconAdvertiser`와 `BeaconObserver` 두 개로
  제공한다. 세 포맷의 공통 wire 처리는 library backend에 두고 Sketch는 송신·관찰 흐름만 보여 준다.
- 두 예제 모두 목적, 준비물, 설정, 실행 순서, 성공 출력, 흔한 오류, 다음 예제의 7개 안내를 가진다.
  실제 센서 대신 BTHome 온도 23.50 °C와 습도 48.00 %를 synthetic 값으로 명시한다.

형식 근거는 Apple의 [iBeacon 시작 문서](https://developer.apple.com/ibeacon/Getting-Started-with-iBeacon.pdf),
Google의 [Eddystone UID 명세](https://github.com/google/eddystone/blob/master/eddystone-uid/README.md),
BTHome의 [v2 format reference](https://bthome.io/format/)다. Apple 상용 인증·브랜딩과
Apple/Google 제품·외장 Beacon 상호운용은 이 build 결과에 포함하지 않는다.

## 3. 로컬 검사 결과

| 검사 | 결과 |
| --- | --- |
| Host C++17 `-Wall -Wextra -Werror` compile와 4개 runtime scenario | PASS |
| 알려진 byte, round-trip, malformed/identifier/version/reserved/range 음성 경계 | PASS |
| 공개 예제 metadata와 생성 안내 189/189 | PASS |
| M31/M32/M33 계약 unit test | PASS, 28/28 |
| M31/M32/M33 원장·계약 drift와 NCS/Zephyr/toolchain lock | PASS |
| Markdown UTF-8·local link | PASS, 482 files |
| NCS 3.4.0 Arduino build — `BeaconAdvertiser` | PASS, Flash 366,780 B, RAM 156,616 B |
| NCS 3.4.0 Arduino build — `BeaconObserver` | PASS, Flash 364,488 B, RAM 156,512 B |
| `M33-BEACON-01:formats` 2보드 20회 × 3형식 × 10광고 | **NOT_RUN** |
| Apple/Google peer·외장 Beacon 상호운용 | **NOT_RUN**, 사용자 후속 |

Host 코덱 검사는 다음 명령으로 재현한다. 이 PC에서는 MSYS2 compiler의 DLL 탐색을 위해
`C:\msys64\ucrt64\bin`을 `PATH`에 함께 넣었다.

```powershell
$env:PATH = 'C:\msys64\ucrt64\bin;' + $env:PATH
$env:CXX = 'C:\msys64\ucrt64\bin\g++.exe'
python tests/host/test_m33_beacon_codec.py
python tests/host/test_rc2_example_guidance.py
python tools/examples/sync_example_guidance.py --check
```

Arduino build는 NCS `C:\ncs\v3.4.0`, toolchain `dcbdc366a1`, BLE profile과
현재 source를 복제한 격리 Arduino platform에서 수행했다. `tests/arduino-cli/run_smoke.py
--tests m33_beacon`이 두 예제를 각각 clean build했고, 마지막 Advertiser source 정리는 같은
cache에서 8/8 재링크해 현재 byte를 다시 확인했다.

## 4. 실패 분석과 남은 위험

1. 첫 target build는 Zephyr minimal C++ 환경에 없는 `<cstring>` 때문에 실패했다. 고정 byte
   복사를 명시적 bounded loop로 바꾸고 Host/target을 다시 검사했다. 이는 제품 source 문제로
   수정 완료했다.
2. 긴 격리 경로에서는 15개 및 2개 작업자 조건 모두 `arm-zephyr-eabi-ar`가 직전에 생성된
   Cracen object를 `No such file or directory`로 열지 못했다. 실제 object 경로 중 하나는 261자였고
   종료 직후 파일이 존재했다. `C:\n54w02`의 짧은 루트에서는 같은 NCS 3.4.0 build 두 개가
   재현 없이 통과했다. 관측 근거는 경로 길이 민감성을 가리키지만 SDK 결함으로 단정하지 않는다.
   HOST-W05는 M33-W06 이후 이 긴 경로 조건을 정식 회귀한다.
3. 세 DAPLink volume의 존재만 확인했으며 probe UID·역할·기존 image는 매핑하지 않았다.
   자동 mass erase, unlock, recover와 upload는 수행하지 않았다. 2보드 HIL 직전에 비식별
   mapping과 역할을 다시 확인해야 한다.
4. W02 완료에는 기존 7개 profile 회귀, 신규 GATT profile 구현·negative·2보드 HIL,
   기존 예제/Fabric catalog 연결이 남아 있다. 따라서 완료 수는 M33 **1/8**을 유지한다.
