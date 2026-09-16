# NU54DK raw CIS/BIS 설치 예제

이 예제는 고정 NCS v3.4.0의 Zephyr Bluetooth ISO API를 Arduino `setup()`/`loop()`에서 직접 사용한다.
Arduino IDE/CLI의 **NU54DK → Feature set → BLE NUS**를 선택한다. 각 폴더의 `prj.conf`는
검증된 role Kconfig를 sketch와 함께 제공한다. 설정 파일이나 SDK source를 임의로 고칠 필요가 없다.
Serial은 115200 baud, LF 종료 ASCII 명령을 사용한다. 한 실기 회차는 32자리 소문자 hex nonce와
100개의 8-byte 검증 SDU로 구성된다. 새 nonce로 `START`하면 자원 반환 후 재시작을 확인할 수 있다.

| 예제 | 보드·역할 | 직접 기능 | 고정 SDK의 upstream origin | 기대 출력 |
| --- | --- | --- | --- | --- |
| `CISCentral` / `CISPeripheral` | 2개, CIG 중앙/주변 | ACL 연결, CIS 생성, SDU 송수신 | Zephyr `samples/bluetooth/iso_central`, `iso_peripheral` | `M31ISO|1|ISO_CONNECTED`, `TX_END` / `RX_END`, `STOPPED` |
| `BISSource` / `BISReceiver` | 2개, BIG 송신/수신 | periodic 광고, BIG/BIS 생성·동기·SDU | Zephyr `samples/bluetooth/iso_broadcast`, `iso_receive` | `M31BIS|1|BIG_SYNCED`, `TX_END` / `RX_END`, `STOPPED` |
| `BISEncryptedSource` / `BISEncryptedReceiver` | 2개, 암호화 BIG 송신/수신 | broadcast code와 MIC 거부·복구 | Zephyr `iso_broadcast`, `iso_receive`의 ISO API | `BAD_CODE_REJECTED`, 정상 code에서 `RX_END` |
| `BISTimeSource` / `BISTimeReceiver` | 2개, BIG 송신/수신 | ISO timestamp/sequence 연속성 | nRF `samples/bluetooth/iso_time_sync` | `TIME_TX_END` / `TIME_END`, `STOPPED` |
| `CISToBISPeer` / `CISToBISBridge` / `CISToBISReceiver` | 3개, CIS 주변→중앙+BIS 송신→수신 | 받은 8-byte CIS SDU를 검증 후 BIS로 전달 | nRF `samples/bluetooth/iso_combined_bis_and_cis` | `M31COMB|1|CIS_RX_END`, `BIS_TX_END`와 수신 `RX_END`, 세 `STOPPED` |

예를 들어 nonce `0123456789abcdef0123456789abcdef`를 사용할 때, CIS 두 보드에
`M31ISO|1|PROBE`, 이어 양쪽에
`M31ISO|1|START|nonce=0123456789abcdef0123456789abcdef|count=100`을 보낸다.
중앙 `TX_END`와 주변 `RX_END`를 확인한 뒤 양쪽에
`M31ISO|1|STOP|nonce=0123456789abcdef0123456789abcdef`을 보낸다.
표시되는 `FAIL` 또는 `RX_BAD_LENGTH`는 성공으로 취급하지 않는다.

BIS는 source `START` → source `BIG_SYNCED` → receiver `START` → receiver `BIG_SYNCED` →
source `M31BIS|1|SEND|nonce=<nonce>` → source `TX_END` → receiver `RX_END` → 양쪽 `STOP` 순서다.
암호화 negative는 receiver에 `M31BIS|1|BAD_CODE`를 `START` 전에 보내고, 송신 후 receiver에
`M31BIS|1|CHECK_BAD_CODE|nonce=<nonce>`를 보내 `BAD_CODE_REJECTED`를 확인한다. 두 보드를
`STOP`한 후 새 nonce로 정상 code 회차를 실행한다. Sync-loss는 정상 BIG 동기 후 receiver에
`M31BIS|1|EXPECT_SYNC_LOSS|nonce=<nonce>`를 보내고 source를 `STOP`하여 `SYNC_LOST`를 확인한다.

세 보드 전달은 peer `M31ISO|1|START|nonce=<nonce>|count=100`와 bridge
`M31COMB|1|START|nonce=<nonce>|count=100`을 보낸 뒤, bridge `CIS_CONNECTED`/`BIG_SYNCED`와
peer `ISO_CONNECTED`를 확인한다. receiver `M31BIS|1|START|nonce=<nonce>|count=100`으로
`BIG_SYNCED`를 기다리고 peer `M31ISO|1|SEND|nonce=<nonce>`를 보낸다. peer `TX_END`, bridge
`CIS_RX_END`/`BIS_TX_END`, receiver `RX_END`를 확인한 후 receiver→peer→bridge 순서로 각각
`STOP|nonce=<nonce>`를 보낸다. controller `empty_slots`는 payload 수신 실패 수가 아니다.

기능 본문은 각각
`tests/zephyr/m31_iso_cis_hil/src/main.cpp`, `m31_iso_bis_hil/src/main.cpp`,
`m31_iso_combined_hil/src/main.cpp`의 검증 source와 byte 동일하다. 공개 header의 바깥 가드는
Arduino CLI의 라이브러리 탐색에서 Zephyr header를 보지 않도록 한다.
`tools/bluetooth/m31_materialize_iso_examples.py`가 source SHA와 예제 구성을 확인한다.
upstream API origin은 고정 Zephyr의 `include/zephyr/bluetooth/iso.h`와 해당 Bluetooth
ISO/BAP sample이다. 이 라이브러리는 편의 facade가 아닌 고급 직접 API이며 Zephyr 유형·Kconfig에
의존한다. 지금 예제는 합성 payload의 RF 전달을 검증하며 LC3, 물리 오디오 출력 또는 제품
상호운용을 주장하지 않는다.
