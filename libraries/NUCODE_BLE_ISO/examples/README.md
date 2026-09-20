# NUCODE BLE ISO 예제

이 11개 역할 예제는 개발 소스 `0.4.1-dev`의 격리 설치본 build와 실제 보드
실행을 완료했다. 현재 설치·지원 package는 `v0.4.1`이며 이 개발 예제들이 그
공개 ZIP에 포함됐다는 뜻은 아니다. 설치본 범위와 exact 증거는
[검증 기록 목차](<../../../00_Docs/04_검증 기록/README.md>)에서 확인한다.

`CISCentral`과 `CISPeripheral`은 `RawCis` 공개 API로 `.ino`에서 8-byte payload를
만들고 검사하는 예제다. 두 보드의 16-byte `sessionId`를 같게 두고 각각 NU54DK Zephyr /
BLE로 빌드한다. Central은 100 frame을 전송하고 Peripheral은 받은 내용과 순서를
검사한다. 각 예제는 종료 뒤 다음 세션을 시작한다.

`BISSource`와 `BISReceiver`도 공개 `RawBis` API로 사용자 8-byte payload를
보내고 검사한다. 두 예제의 16-byte `sessionId`를 같게 두며 source가 방송을
시작한 뒤 receiver가 같은 광고에 동기화한다. 수신 측은 빠진 packet을 별도로
세고, 매 회차 99개 이상·손상 0개를 확인한 후 다시 시작한다.

`BISEncryptedSource`와 `BISEncryptedReceiver`는 같은 데이터 흐름에 별도의
16-byte `broadcastCode`를 더한다. 두 `.ino`의 Code가 일치해야 하며 실제
사용자는 예제 값을 새 값으로 바꾸어야 한다. 잘못된 Code에서는 MIC가 수신 SDU를
거부한다.

`BISTimeSource`는 첫 SDU 완료의 HCI 시각을 읽고 다음 99개 SDU에 명시 시각을
붙인다. `BISTimeReceiver`는 받은 payload와 시각의 유효성·단조 증가를 검사한다.
두 예제의 `sessionId`가 같아야 한다.

`CISToBISPeer`·`CISToBISBridge`·`CISToBISReceiver`는 세 보드에서 각각
CIS payload 생성, CIS 수신→BIS 전달, BIS 수신을 수행한다. Peer와 bridge의
`cisSessionId`, bridge와 receiver의 `bisSessionId`가 각각 일치해야 한다.
Receiver는 첫 부팅에서 이전 BIG의 해제를 기다린 뒤 동기화를 시작한다.

11개 `.ino`는 모두 payload 생성·검사, 시작·전송·수신·오류·종료 흐름을 공개
`RawCis`/`RawBis` API로 보여 준다. Bluetooth ISO 객체, Zephyr callback과
buffer 관리는 라이브러리 구현 내부에 있다. [재점검 기록](<../../../00_Docs/04_검증 기록/191_M31_W02_공개_ISO_예제_재점검.md>)과
[CIS 실기](<../../../00_Docs/04_검증 기록/192_M31_W02_공개_CIS_사용자_SDU_실기.md>),
[일반 BIS 실기](<../../../00_Docs/04_검증 기록/193_M31_W02_공개_BIS_사용자_SDU_실기.md>),
[암호화 BIS 실기](<../../../00_Docs/04_검증 기록/194_M31_W02_공개_암호화_BIS_사용자_SDU_실기.md>),
[시각 동기 실기](<../../../00_Docs/04_검증 기록/195_M31_W02_공개_BIS_시각동기_사용자_SDU_실기.md>),
[세 보드 전달 실기](<../../../00_Docs/04_검증 기록/196_M31_W02_공개_CIS_BIS_세_보드_사용자_SDU_실기.md>)에
각 역할의 exact build·실행 범위를 기록했다.

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

이전 고정 시험 backend의 115200 baud Serial 명령 형식은 회귀 시험용 구현
세부사항이며 Arduino 공개 API나 호환성 계약에는 포함되지 않는다. 현재 11개
예제는 Serial 명령에 의존하지 않고 `RawCis`/`RawBis` API를 직접 사용한다.

## 출처와 라이선스

역할별 동작은 고정 NCS v3.4.0의 Zephyr `samples/bluetooth/iso_*`와 nRF
`samples/bluetooth/iso_combined_bis_and_cis`를 기준으로 검증했다. NUCODE 라이브러리 코드는
MIT이고, 원본 sample은 각 원본의 Apache-2.0 라이선스를 따른다.
