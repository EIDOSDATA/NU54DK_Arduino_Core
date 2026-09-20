# M31-W03 Arduino BAP unicast LC3 재시작 복구 20회

clean Core `1f560fed1bb889b5def834e88c62d18939db2e4e`에서 공개
`BapUnicastSource`와 `BapUnicastSink`를 다시 빌드했다. Source HEX SHA-256은
`4324948cbe0e9899e89f0ada170886441baea1d65ea1a56a5fd5ca6bb77d91a2`,
Sink는 `53cfdadc8de7276ac6fb00def4dc1e6c61a5b5097d48e6f3d4026b46048fd8c8`이다.
두 이미지의 `CONFIG_BT_TX_PROCESSOR_STACK_SIZE=3200`과 LC3/FPU가 설정에 있다.
Source는 FLASH 501,752 B·RAM 227,237 B, Sink는 FLASH 474,736 B·RAM 227,320 B다.
두 역할 모두 256 KiB RAM의 약 86%를 쓴다.

두 CMSIS-DAP V2 probe의 익명 SHA-256 mapping을 확인하고 sector flash와 hardware
reset만 사용했다. [플래시 기록](evidence/m31-w03-bap-arduino-recovery-1f560fed/flash.json)과
[독립 reset 1,000 frame 측정](evidence/m31-w03-bap-arduino-recovery-1f560fed/pair-exact.json)을
분리했다. 후자에서 source TX 1,000개, sink LC3 복호화 1,000개, PCM energy
1,159,890, queue drop 0을 15.422초에 확인했다.

별도 [재시작 시험](evidence/m31-w03-bap-arduino-recovery-1f560fed/recovery-exact.json)은
sink 보드를 hardware reset한 뒤 광고, source 연결 해제·재스캔·재접속,
LC3 TX/RX 각 100 frame 이상을 **20회 연속** 확인했다. 20회 모두 통과했고
회복 시간은 회당 11.562~12.109초로 30초 한도 이내다. 시험은 원본 probe UID를
보존하지 않았고, [manifest](evidence/m31-w03-bap-arduino-recovery-1f560fed/manifest.json)의
파일 해시와 압축 HEX/설정 해시를 실행 JSON과 대조했다.

초기 재접속에서는 source가 스캔을 재개하지 못했다. duplicate filter를 끈
공개 스캔 API로 재시작하도록 수정했다. 이후 재접속 중 stack overflow를
CMSIS-DAP V2와 GDB로 확인했다. 당시 `_kernel.cpus[0].current`는
`bt_tx_processor_workq`였고 stack 크기는 `0x388`(904 B), Kconfig는
`CONFIG_BT_TX_PROCESSOR_STACK_SIZE=900`이었다. 두 역할의 TX processor
stack을 3,200 B로 지정한 뒤 같은 재접속 경로가 진행됐다. 또한 상대
보드 재시작으로 bond가 불일치할 때 보안 error 2 또는 4를 받은 해당 peer의
bond만 지우고 새 연결에서 다시 페어링하도록 했다. 제어된 reset 직후
일시적인 보안/전송 실패 로그는 생길 수 있으나, 위 판정은 새 연결의
실제 LC3 frame 전송·복호화 완료를 요구한다.

`m31_example_audit.py`는 79개 예제·문제 0개, M31 Host 49개와 M31
contract가 통과했다. CI/CD는 조회하지 않았다. 이 결과는 **BAP unicast
단방향 Arduino 두 역할과 sink reset 복구**의 증거다. 양방향 Arduino
stream, 명시적 stop/release 20회, 잘못된 ASE 상태·codec/QoS 거부와
다른 W03 profile은 아직 완료하지 않았다. W03-01/02 전체
`functional_hil` 또는 M31-W03 완료로 승격하지 않는다.
