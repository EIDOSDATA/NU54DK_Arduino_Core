# Nordic RAS 실기 비교 fixture

고정 NCS `v3.4.0`의 `ras_initiator`·`ras_reflector` 원본을 SDK 디렉터리 밖으로
복사하고, [계측 patch](native-instrumentation.patch)로 callback/abort/busy와
RAS counter를 기록한다. 원본의 거리 추정 및 무선 경로는 유지하며 UART `s` 명령으로
CS disable·ACL disconnect·광고 중단과 양측 `NATIVE_CS_STOP`을 확인한다.
**원본 sample 자체는 disconnect 때 reboot하므로 이 HIL runner에 flash하지 않는다.**

```powershell
python tests/hil/nu54dk/fixtures/NordicRasComparison/prepare.py `
    --ncs-root C:\ncs\v3.4.0 --output C:\r31k\native-ras-fresh
```

`prepare.py`는 SDK source SHA-256을 먼저 검사하고 기존 출력 디렉터리에는
덮어쓰지 않는다. 적용 후 LF 기준 계측 source hash도 검사한다. `west build`의
target은 `nrf54l15dk/nrf54l15/cpuapp/nu54dk`, `BOARD_ROOT`는 이 저장소의
`board_package/NU54DK_Zephyr_DTS`다. 두 역할의 `zephyr.hex`를 빌드한 뒤
정확한 probe UID/COM mapping과 image hash를 확인하고
[`p2_cs_native_comparison_run.py`](../../p2_cs_native_comparison_run.py)를 실행한다.
sector flash에는 `auto_unlock=false`를 사용하며 mass erase·recover를 금지한다.

이 fixture는 Nordic **원본과 byte-identical**하지 않다. 계측·STOP 코드가 추가되고
reboot 동작을 바꿨다. Arduino raw RTT 경로와도 DSP·stack·malloc 설정이 달라
FLASH/RAM 차이를 그대로 Arduino 오버헤드로 계산하지 않는다. 비교 범위와
원본 결과는 [250번 기록](<../../../../../00_Docs/04_검증 기록/250_M31_P2_native_CS_비교와_DF_재진단.md>)에 둔다.
