# NUCODE BLE ISO 예제

`CISCentral`과 `CISPeripheral`은 `RawCis` 공개 API로 `.ino`에서 8-byte payload를
만들고 검사하는 예제다. 두 보드의 16-byte `sessionId`를 같게 두고 각각 NU54DK Zephyr /
BLE로 빌드한다. Central은 100 frame을 전송하고 Peripheral은 받은 내용과 순서를
검사한다. 각 예제는 종료 뒤 다음 세션을 시작한다.

`BISSource`와 `BISReceiver`도 공개 `RawBis` API로 사용자 8-byte payload를
보내고 검사한다. 두 예제의 16-byte `sessionId`를 같게 두며 source가 방송을
시작한 뒤 receiver가 같은 광고에 동기화한다. 수신 측은 빠진 packet을 별도로
세고, 매 회차 99개 이상·손상 0개를 확인한 후 다시 시작한다.

나머지 7개 스케치는 고정 시험 SDU를 실행하는 진단 역할 예제다. `.ino`에서 사용자
payload를 송수신하는 공개 API를 아직 사용하지 않으므로 일반 Arduino 데이터 예제로
간주하지 않는다. [재점검 기록](<../../../00_Docs/04_검증 기록/191_M31_W02_공개_ISO_예제_재점검.md>)과
[CIS 두 역할 실기](<../../../00_Docs/04_검증 기록/192_M31_W02_공개_CIS_사용자_SDU_실기.md>),
[BIS 두 역할 실기](<../../../00_Docs/04_검증 기록/193_M31_W02_공개_BIS_사용자_SDU_실기.md>)에
W02 재작업 범위와 검증 결과를 기록했다.

`CISCentral`/`CISPeripheral`과 `BISSource`/`BISReceiver`의 `.ino`에는 payload
생성·검사, 시작·전송·수신·오류·종료 흐름이 있다. Bluetooth ISO 객체,
Zephyr callback과 buffer 관리는 라이브러리 구현 내부에 있다. 다른 역할은 공개
데이터 API로 전환하는 중이다.

| 예제 | 보드 수 | 역할 |
|---|---:|---|
| `CISCentral` / `CISPeripheral` | 2 | 연결형 ISO 송수신 |
| `BISSource` / `BISReceiver` | 2 | Broadcast ISO 송수신 |
| `BISEncryptedSource` / `BISEncryptedReceiver` | 2 | broadcast code를 사용하는 암호화 BIS |
| `BISTimeSource` / `BISTimeReceiver` | 2 | timestamp를 포함한 BIS 송수신 |
| `CISToBISPeer` / `CISToBISBridge` / `CISToBISReceiver` | 3 | CIS SDU를 BIS로 전달 |

각 예제의 `prj.conf`는 한 역할을 `CONFIG_NUCODE_BLE_ISO_MODE_*` Kconfig로 선택한다.
스케치의 `Role` 값과 image의 역할이 다르면 공개 객체의 `begin()`이
`Error::configuration_mismatch`를 반환한다. Arduino IDE나 CLI에서 **NU54DK Zephyr / BLE**
feature set을 선택해 빌드한다.

남은 진단 역할의 115200 baud Serial 명령 형식은 회귀 시험용 구현 세부사항이며
Arduino 공개 API나 호환성 계약에는 포함되지 않는다. 새 CIS/BIS 예제는 Serial 명령에
의존하지 않고 `RawCis`/`RawBis` API를 직접 사용한다.

## 출처와 라이선스

역할별 동작은 고정 NCS v3.4.0의 Zephyr `samples/bluetooth/iso_*`와 nRF
`samples/bluetooth/iso_combined_bis_and_cis`를 기준으로 검증했다. NUCODE 라이브러리 코드는
MIT이고, 원본 sample은 각 원본의 Apache-2.0 라이선스를 따른다.
