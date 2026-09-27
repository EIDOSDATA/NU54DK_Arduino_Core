# M31-W03 Arduino BAP 양방향 client/server와 단방향 회귀

clean Core `d29ee27e61acf600b6792282be8d0c3d3bf50a1c`에서 공개
[`BapUnicastDuplexClient`](../../libraries/NUCODE_BLE_Audio/examples/BapUnicastDuplexClient/BapUnicastDuplexClient.ino)와
[`BapUnicastDuplexServer`](../../libraries/NUCODE_BLE_Audio/examples/BapUnicastDuplexServer/BapUnicastDuplexServer.ino)를
각각 NU54DK Zephyr / BLE로 빌드했다. `.ino`는 일반 C++로 PCM을 만들고
`NUCODE_BLE_Audio` API로 LC3 encode/send 및 receive/decode를 수행한다.
PACS/ASCS·CIS와 Zephyr 호출은 library `.cpp`에 있다. 기존 단방향
`UnicastClient::begin(connection)`과 `UnicastServer::begin()`의 진입점은
보존하고, 요청한 역할에만 양방향 모드를 적용한다.

양쪽 CMSIS-DAP V2 probe를 익명 SHA-256 mapping으로 선택했다. client는
FLASH 519,228 B·RAM 230,830 B(88%), server는 FLASH 515,504 B·RAM
231,579 B(88%)다. 고정 SDK가 client ASE 검색 용량을 방향별 0 또는
2개 이상으로 요구하므로 profile은 각 방향 2개를 예약하고 실제 한 쌍의
stream을 사용한다. 추가 stream·외장 audio I/O는 별도 자원 예산 없이 이
profile에 더하지 않는다.

[client flash](evidence/m31-w03-bap-duplex-pair-d29ee27e/duplex-client-flash.json)와
[server flash](evidence/m31-w03-bap-duplex-pair-d29ee27e/duplex-server-flash.json)의
HEX hash는 clean source에서 재빌드한 이미지와 byte 단위로 같았다. 각 역할을
sector flash한 뒤 별도의 hardware reset으로 측정했다.
[양방향 pair 원본](evidence/m31-w03-bap-duplex-pair-d29ee27e/duplex-pair-exact.json)에서
client TX→server RX 1,000 frame과 server TX→client RX 1,000 frame을
모두 확인했다. client/server 복호화 PCM energy는 각각 1,174,747 /
1,159,890, queue drop은 양쪽 모두 0, 측정 시간은 18.235초다.

[양방향 종료·재연결 원본](evidence/m31-w03-bap-duplex-pair-d29ee27e/duplex-cycle-exact.json)은
각 연결에서 양쪽 송수신 100 frame 이상을 확인한 뒤 client Serial `s`로
두 ASE를 disable·release하고 ACL 해제 뒤 재연결하는 20/20회다. 회차별
완료 시간은 8.609~13.500초로 30초 복구 한도 이내였다. client의
`sent frames=100`, `received=100 ... dropped=0`, `stream stopped`가
각각 20회 나타났다.

기존 단방향 경로도 같은 clean source에서 다시 빌드·flash했다.
[source→sink 1,000 frame](evidence/m31-w03-bap-duplex-pair-d29ee27e/source-sink-exact.json)은
PCM energy 1,159,890, drop 0으로 통과했다.
[기존 종료·재연결 20회](evidence/m31-w03-bap-duplex-pair-d29ee27e/source-cycle-exact.json)는
sink 복호화 2,400 frame, 중복 stop·중단 중 전송 거부 40/40, 회차별
5.859~6.657초로 통과했다. 따라서 새 callback 상태 기계가 기존 공개
송신 API와 stop/release 경로를 깨지 않았음을 보드에서 확인했다.

초기 종료 시험에는 세 가지 무효/실패 attempt가 있었다. 재설정 전 Serial
잔류 로그를 읽은 시도, 종료 **전** 해제를 종료 후 해제로 잘못 세어 PASS를
출력한 시도, 정상 종료 중 server `not_ready`를 실패로 출력한 시도다.
[진단 원본과 제외 사유](evidence/m31-w03-bap-duplex-pair-d29ee27e/provenance-audit.json)를
보존하고 완료 분자에서 제외했다. 검증기는 종료 후 해제 순서와 flash
이미지 hash를 검사하도록 고쳤다.
[manifest](evidence/m31-w03-bap-duplex-pair-d29ee27e/manifest.json)는
각 HEX/.config, build log와 원본 JSON의 SHA-256을 연결한다.

앞선 원격 unsupported codec·invalid QoS·idle ASE 상태 거부 증거와
이번 양방향/단방향 회귀를 합쳐 W03-02 BAP unicast/PACS/ASCS의
개발용 기능 HIL을 완료로 판정한다. W03-03~11의 broadcast·BASS·CAP 등
나머지 profile과 외장 audio I/O 구현은 계속 미완료이므로 M31-W03 전체는
진행 중이다. CI/CD는 조회하지 않았다.
