# M31-W05 RAS native 100회 진단

고정 NCS `v3.4.0`의 `ras_initiator`와 `ras_reflector` sample을 NU54DK board revision
`fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`으로 각각 native target build했다.
빌드와 HEX 원본의 SHA-256, 압축 로그·이미지, 두 보드 UART의 익명화 원본은
[manifest](evidence/m31-w05-ras-native-96de07ba/native-ras-manifest.json)에 묶었다.
initiator는 FLASH 290180 B/RAM 67352 B, reflector는 FLASH 247840 B/RAM 53574 B다.
두 이미지 모두 `CONFIG_BT_CHANNEL_SOUNDING=y`와 `CONFIG_BT_RAS=y`를 포함한다.

첫 실행에서 sector flash 뒤 역할별 hardware reset을 연속 수행하자, initiator가 secure ACL
level 2, RAS feature `0x1`, CS capability/config/security를 교환하고 유한한 거리 추정 33회를
출력한 뒤 다시 부팅했다. reflector는 뒤이어 procedure buffer 할당 실패를 출력했다.
이 [실패 원본](evidence/m31-w05-ras-native-96de07ba/native-probe.json)을 성공으로 덮어쓰지 않는다.
이전 `connected_cs` 진단에서는 instrumented firmware의 재부팅 시
`RESETREAS.RESETPIN=1`을 관찰했지만, 해당 실행만으로 물리 reset 원인을 특정하지 못했다.

동일한 두 이미지와 두 보드를 다시 flash하지 않고 **양쪽 hardware reset만 새로 수행한**
[두 번째 진단](evidence/m31-w05-ras-native-96de07ba/reset-probe.json)에서는 11.735초 안에
initiator가 결과 출력 100개를 남겼다. `ifft`, `phase_slope`, `rtt`의 100개 triple은
모두 파싱 가능하고 유한했다. 이 구간에서 양쪽 boot banner는 각각 1개였고 reflector의
buffer 할당 실패와 오류 출력은 0개였다. 거리는 정확도 또는 보정 결과로 해석하지 않는다.

이 결과는 **NCS native RAS 경로의 연결·자료 교환 적용성**을 입증하는 진단이다. UART 출력
100개를 Arduino API의 procedure 100회 성공이나 W05 완료로 승격하지 않는다. 실행 runner는
로컬 임시 Python 진단본이므로 `source_clean=false`이며, 공개 Arduino initiator/reflector
sketch·RAS wrapper·중단/재시작 20회·peer loss 및 미인증/wrong-peer negative는 남아 있다.
다음 구현에서는 공통 `NUCODE_BLE`의 연결 handle과 `NUCODE_BLE_Security`를 이용하고,
Zephyr·RAS 직접 호출은 library `.cpp` 내부에만 둔다.
