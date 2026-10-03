# Ranging Service reflector

이 예제는 정식 `v0.5.0`에 포함되며 Channel Sounding 검증을 완료했다.
Windows 10/11 x64 설치 방법은 [v0.5.0 안내](<../../../../00_Docs/05_릴리스/v0.5.0/README.md>)를 따른다.
아래 준비 상태는 거리 정확도·cross-vendor 상호운용 보증이 아니다.

보드 **NU54DK (nRF54L15, Zephyr)**, Feature set **BLE NUS**를 권장한다.
**Adaptive capabilities (experimental)**는 실험적 대안이다. NU54DK 두 대에 Reflector와
Initiator를 각각 업로드하고 Reflector를 먼저 켠다. `nucode-build.json`과 `prj.conf`를 `.ino`와
함께 유지한다. 여러 probe를 연결한 CLI Upload는 `NUCODE_PROBE_UID`로 exact UID를 지정하며,
GUI Upload는 한 번에 대상 보드 한 대만 연결한다. 업로드 후에는 두 보드를 모두 연결해 실행한다.

고정 NCS v3.4.0 제품 SDC에서 secure raw 100건, stop/restart·disconnect/reconnect 각 20/20,
256-step 유효 raw 1,000건과 peer-loss 복구를 확인했다. reflector bond만 삭제한 negative에서는
새 pairing·L2·ready·active·raw 없이 양쪽 STOP으로 정리됐다.

이 스케치는 `NU54-CS-RSP` 이름과 Ranging Service UUID `0x185B`로 연결 가능한
광고를 시작합니다. 중앙 장치가 연결되면 공개 `RasReflector` API가 기본 안테나의
CS 설정과 Ranging Service 응답을 준비합니다. 연결이 끊어지면 자원을 반환하고
다시 광고합니다.

Serial Monitor는 115200 baud입니다. `secure L2`, `config ready`,
`CS procedures enabled` 출력은 단계별 상태를 뜻합니다. 거리 측정값은
initiator에서 계산하며, 이 스케치 자체가 거리값을 만들지는 않습니다.
