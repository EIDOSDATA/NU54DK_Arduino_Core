# M30-W05 MCUboot layout·서명 완료

## 결과

M30-W05를 고정 board `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`, NCS v3.4.0에서
완료했다. 기존 loaderless profile은 변경하지 않고 별도 `secure_ble_dfu` profile에 MCUboot와
dual-slot layout을 추가했다. exact Core `b16b44f405ee8617a675cae9f5dfcc027f03816a`에서 외부
ECDSA P-256 키로 서명한 image의 부트 20회, unsigned image와 다른 키로 서명한 image의 거부를
실제 보드에서 확인했다.

| Gate | 결과 |
| --- | --- |
| W05 Host 계약 | **10/10 PASS** |
| 전체 Host 회귀 | **1,238 tests PASS, 2 skipped** |
| Arduino `m30secure` 예제 | **1/1 build PASS** |
| secure profile target | **CI 기본키·외부 개발키 sysbuild PASS** |
| 실제 `M30-BOOT-01` | **signed boot 20/20** |
| unsigned image 수용 | **0** |
| wrong-key image 수용 | **0** |
| M30 진행률 | **W05 완료, 작업 묶음 5/8·test ID 6/10 PASS** |

## profile과 flash layout

`secure_ble_dfu`는 sysbuild로 application과 MCUboot를 함께 만들며 ECDSA P-256 서명을 요구한다.
일반 `standard`, `ble`, `fabric` profile은 loaderless 상태를 유지한다.

| 영역 | offset | 크기 |
| --- | ---: | ---: |
| MCUboot | 0 | 63,488 bytes |
| slot 0 | 65,536 | 729,088 bytes |
| slot 1 | 794,624 | 729,088 bytes |
| storage | 1,523,712 | 36,864 bytes |

builder는 sysbuild domain, signed artifact, linker·manifest·export 값을 fail-closed로 검사한다.
개발·생산 private key는 저장소 밖의 PEM만 허용하고 `NUCODE_DFU_SIGNING_KEY`로 전달한다. cache와
증적에는 공개키 source hash만 남기며 private key, raw probe UID, OOB 비밀은 기록하지 않는다.
MCUboot는 swap-using-move, image security counter와 confirmed image 정책을 사용한다.

## 실제 시험

F:/COM14의 고정 보드 한 대에서 bootloader와 primary signed image를 exact sector 방식으로 쓰고,
서명된 confirmed image가 20번 연속 기동하는지 확인했다. 이어 raw unsigned application image와
별도 P-256 키로 서명한 9.0.0 image를 slot 1에 각각 넣었으며 두 image 모두 선택·부트되지 않았다.
실행 시간은 61.156초였다. raw probe UID 대신 SHA-256만 보존했다.

시험이 지운 범위는 slot 1의 `0x0c2000` 이상 `0x174000` 미만 sector뿐이다. chip/mass erase,
recover와 실제 전원 차단은 수행하지 않았다. reset 또는 reboot를 전원 차단 증거로 계산하지 않는다.

- [구조화 evidence](evidence/m30-w05-b16b44f4-boot/m30-boot-01.json)
- [target transcript](evidence/m30-w05-b16b44f4-boot/m30-boot-01.transcript.log)

## 실패와 수정

- PowerShell이 native argument의 drive colon 뒤를 분리한 첫 build 명령은 hardware 접근 전에
  실패했다. 이후 argument array로 고정했다.
- NCS 환경을 system Python에 주입한 실행은 pySerial runtime 충돌로 flash 전에 중단됐다.
  image tool만 격리된 NCS child 환경에서 실행하도록 수정했다.
- 최초 실제 image는 부트와 `READY`까지 확인했지만 polling UART 수신이 명령을 안정적으로 받지
  못했다. 실패 transcript는 저장소 밖 작업 보존 경로로 분리하고 target protocol을 검증된 Arduino
  Core IRQ `Serial`로 변경한 exact commit을 다시 build해 전체 시험을 처음부터 수행했다.

각 실패는 원인 분류와 단일 수정 뒤 재검증했다. 무한 재시도, mass erase/recover 또는 전원 차단
대체 주장은 없었다.

## 다음 작업

M30은 **5/8 작업 묶음, 6/10 test ID PASS**다. M30-W06에서 인증·암호화된 BLE link 위의 SMP
DFU, 정상 update 10회, 다섯 negative class와 rollback 거부를 구현·검증한다. W07 통합 HIL까지
자동 진행하고, 실제 target USB 전원 차단은 `M30-POWER-01` 주입 직전에 멈춘다.
