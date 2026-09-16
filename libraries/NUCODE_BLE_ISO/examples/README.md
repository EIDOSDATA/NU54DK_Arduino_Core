# NUCODE BLE ISO 예제

> 현재 11개 스케치는 고정 시험 SDU를 실행하는 진단 역할 예제입니다. 사용자 payload를
> `.ino`에서 송수신하는 공개 API가 아직 없으므로 일반 Arduino 데이터 예제로 사용하지
> 마세요. [재점검 기록](<../../../00_Docs/04_검증 기록/191_M31_W02_공개_ISO_예제_재점검.md>)에
> W02 재작업 범위를 기록했습니다.

이 예제들은 `NUCODE_BLE_ISO.h`의 공개 Arduino API로 CIS, BIS와 CIS-BIS 전달 역할을
실행한다. `.ino`에는 역할 선택, 초기화, 오류 처리와 `poll()` 흐름이 보인다. Bluetooth
ISO 객체, Zephyr callback, work queue와 buffer 관리는 라이브러리 구현 내부에 있다.

| 예제 | 보드 수 | 역할 |
|---|---:|---|
| `CISCentral` / `CISPeripheral` | 2 | 연결형 ISO 송수신 |
| `BISSource` / `BISReceiver` | 2 | Broadcast ISO 송수신 |
| `BISEncryptedSource` / `BISEncryptedReceiver` | 2 | broadcast code를 사용하는 암호화 BIS |
| `BISTimeSource` / `BISTimeReceiver` | 2 | timestamp를 포함한 BIS 송수신 |
| `CISToBISPeer` / `CISToBISBridge` / `CISToBISReceiver` | 3 | CIS SDU를 BIS로 전달 |

각 예제의 `prj.conf`는 한 역할을 `CONFIG_NUCODE_BLE_ISO_MODE_*` Kconfig로 선택한다.
스케치의 `Role` 값과 image의 역할이 다르면 `Program::begin()`이
`Error::configuration_mismatch`를 반환한다. Arduino IDE나 CLI에서 **NU54DK Zephyr / BLE**
feature set을 선택해 빌드한다.

프로그램은 115200 baud Serial로 유한 검증 세션을 제어할 수 있다. 이 명령 형식은
회귀 시험용 구현 세부사항이며 Arduino 공개 API나 호환성 계약에는 포함되지 않는다.

## 출처와 라이선스

역할별 동작은 고정 NCS v3.4.0의 Zephyr `samples/bluetooth/iso_*`와 nRF
`samples/bluetooth/iso_combined_bis_and_cis`를 기준으로 검증했다. NUCODE 라이브러리 코드는
MIT이고, 원본 sample은 각 원본의 Apache-2.0 라이선스를 따른다.
