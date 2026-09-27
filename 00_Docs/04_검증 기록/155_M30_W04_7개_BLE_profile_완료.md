# M30-W04 일곱 BLE profile 완료

## 결과

M30-W04를 고정 board `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`, NCS v3.4.0에서
완료했다. 기존 BAS·DIS·HID keyboard를 회귀하고 HID mouse, HID consumer-control, Heart Rate
Service와 Environmental Sensing Service를 추가했다. exact Core
`d2a0b96888bd2f7c75d6ed02d46c0a3751e2d283`의 두 역할 image로 실제 암호화 BLE link에서
catalog 7개와 서비스별 operation 100회를 확인했다.

| Gate | 결과 |
| --- | --- |
| W04 Host 계약·parser | **6/6 PASS** |
| Arduino profile 예제 | **4/4 build PASS** |
| peripheral/central target | **2/2 PASS, warning 0** |
| 실제 `M30-PROFILE-01` | **catalog 7/7, 서비스별 100 operation** |
| central payload 오류 | **0** |
| peripheral driver 오류 | **0** |
| M30 진행률 | **W04 완료, 작업 묶음 4/8·test ID 5/10 PASS** |

## 구현 경계

- 하나의 정적 HIDS database가 keyboard report ID 1/8 byte, mouse ID 2/4 byte,
  consumer-control ID 3/2 byte를 제공한다. 각 facade의 `begin()` 상태는 고정 bit로 분리하며 heap을
  사용하지 않는다.
- keyboard boot protocol은 기존 8-byte report만 허용한다. boot mode에서 mouse와
  consumer-control 전송은 `invalid_state`로 거부한다.
- HRS는 표준 `0x180D` service와 암호화된 measurement notification을 사용한다. 공개 facade는
  1~240 bpm만 허용한다.
- ESS는 표준 `0x181A` service에 temperature `0x2A6E`와 humidity `0x2A6F`를 정적 attribute로
  제공한다. read와 CCC write는 L2 이상 암호화가 필요하다.
- 공개 예제는 `SecureMouse`, `SecureConsumerControl`, `HeartRate`, `EnvironmentalSensing`이며
  개별 Zephyr sidecar 없이 library include가 `nucode.ble.security` feature를 선택한다.

## 실제 시험

peripheral은 BAS, keyboard, mouse, consumer-control, HRS, ESS temperature와 humidity notification을
각각 100회 전송했다. central은 세 HIDS report를 각각 분류하고 BAS·HRS·ESS payload 순번과 값을
검사했으며 DIS manufacturer characteristic을 실제 GATT read로 100회 읽었다. 이로써 ESS의 두
characteristic은 각각 100회 검증하되 catalog 분모에서는 하나의 ESS profile로 계산했다.

실행 시간은 44.167초였다. 두 보드는 F:/COM14 peripheral과 G:/COM10 central로 사용했으며 raw
probe UID 대신 SHA-256만 증적에 남겼다. sector flash만 사용했고 mass erase/recover, warm reboot와
실제 전원 차단은 수행하지 않았다.

- [구조화 evidence](evidence/m30-w04-d2a0b968-profile/m30-profile-01.json)
- [peripheral transcript](evidence/m30-w04-d2a0b968-profile/m30-profile-01.peripheral.transcript.log)
- [central transcript](evidence/m30-w04-d2a0b968-profile/m30-profile-01.central.transcript.log)

## 실패와 수정

첫 실제 실행에서 peripheral legacy advertising과 central extended scan API가 맞지 않아 central이
`scan-start`로 즉시 실패했다. 프로파일 operation이 시작되기 전 fail-closed로 중단됐고 실패
transcript는 작업 보존 경로로 분리했다. central을 legacy passive scan으로 맞춘 새 exact commit을
빌드해 전체 시험을 처음부터 다시 실행했다. 재시도 횟수로 성공을 만들거나 reset을 전원 차단
증거로 사용하지 않았다.

## 다음 작업

M30은 **4/8 작업 묶음, 5/10 test ID PASS**다. 다음은 M30-W05에서 기본 loaderless profile을
보존하면서 별도 secure BLE DFU profile의 MCUboot dual-slot layout, 외부 ECDSA P-256 개발키,
서명·wrong-key·unsigned 거부와 20회 signed boot를 구현·검증한다. 실제 target USB 전원 차단은
W07까지 완료하고 `M30-POWER-01` 주입 직전에만 요청한다.
