# M31-W03 Arduino CAP unicast 반복 실기

공개 `CapUnicastInitiator`와 `CapUnicastAcceptor`를 exact source
`23afdc432d43f42fc23c29d282caa5d5407d5401`에서 clean build했다. 두 공개 `.ino`는
NUCODE C++ API로 CAS/PACS/ASCS 검색, CAP start/cancel/stop, LC3 encode/decode와 재연결을
수행하며 Zephyr 직접 호출이나 개발 milestone 표식을 포함하지 않는다.

## 고정 입력과 build

NCS nRF `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr
`bf801e4e3d19e1ffa76164346480cb7734dd2800`, board submodule
`fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`, toolchain `dcbdc366a1`을 고정했다.

| 역할 | Flash | RAM | HEX SHA-256 | HEX bytes |
| --- | ---: | ---: | --- | ---: |
| Initiator | 512,356 B (34%) | 229,356 B (87%) | `2d5fd1ddec3b0222fa9686a6ef1597dd8c7472f0a49927e2ecb0bcbe9d760907` | 1,441,294 |
| Acceptor | 475,928 B (31%) | 228,637 B (87%) | `79af4a0075fad61dbac0923a98f7ce527ef69789a002c2a62cfe939d99296bb0` | 1,338,863 |

새 PC에서 CMSIS-DAP V2 원문 UID는 저장하지 않고 SHA-256 identity로 Initiator와 Acceptor를
선택했다. target UART 역할은 각각 COM10과 COM14로 다시 확인했다. DAPLink MSD 전송 중 한
시도는 `Last Flash Error: The transfer timed out.`와 1,048,576 byte를 보고했다. 이를 전원
문제로 추정하지 않았고 같은 exact HEX를 다시 전송해 두 역할 모두 `SUCCESS`와 전체 HEX byte를
확인한 뒤 실기를 시작했다.

## CAP procedure와 실제 LC3

두 보드를 reset 시점부터 동시에 캡처했다. Acceptor는 BLE, CAS, unicast server, LC3 codec과
연결 광고 준비를 순서대로 출력했고 Initiator는 CAS와 PACS/ASCS 검색 뒤 CAP group start를
수행했다. 240.016초 동안 다음 결과를 얻었다.

| 확인 항목 | 결과 |
| --- | ---: |
| CAP start → CIS 송신 → stop 완료 | **23회** |
| 진행 중 start 절차 cancel callback | **22회** |
| stop 직후 duplicate stop 거부 | **23회** |
| disconnect 뒤 새 연결 | **48회** |
| Acceptor LC3 decode 확인 | **1,800 frame** |
| Acceptor queue drop | **0** |
| CAP procedure failure | **0** |

각 송신 회차는 `CAP sent frames=100`, 정상 stop과 공개 오류값 `duplicate=8`을 출력했다.
Acceptor는 100 frame 단위의 PCM energy와 `dropped=0`을 보존했다. cancel 회차는
`CAP procedure cancelled native=0` callback을 받은 뒤 연결을 반환하고 새 광고를 다시
검색했다. 따라서 start/cancel/stop, 실제 CIS payload, release와 재연결의 반복 경로를 각각
20회 이상 확인했다.

[구조화 manifest](evidence/m31-w03-cap-unicast-23afdc43/manifest.json)와
[UART transcript](evidence/m31-w03-cap-unicast-23afdc43/cap-unicast-transcript.log)에 exact image,
안전한 probe identity, 분모와 원시 상태 전이를 보존했다. Manifest의 최소 decode 기준은
1,000 frame이며 실제 결과는 1,800 frame이다. 송신 회차마다 stop을 시작한 직후 남은 controller
queue를 모두 수신한다고 가정하지 않으므로 송신 100 frame과 decode 누적값의 일대일 동일성은
합격 기준으로 사용하지 않았다.

## 진단과 남은 경계

초기 reset 이후 UART를 늦게 열어 setup 한 번 출력이 보이지 않았던 상태는 전원 문제로 판정하지
않았다. CFSR/HFSR는 0이었고 reset 전에 잡힌 GRTC PC도 정상 실행 image에서 같은 timer read
위치로 관찰됐다. UART를 먼저 열고 reset 직후부터 캡처하자 BLE·CAS·server·codec·광고 준비와
주기 상태가 모두 출력됐다. 따라서 추측성 GRTC 또는 전원 결함 판정은 폐기하고 실제 runtime
로그를 최종 근거로 사용한다.

공개 API의 group은 고정 SDK 자원 계약상 Acceptor 1개인 ad-hoc group이다. 이 범위에서 handover는
기존 연결의 stop/release/disconnect 뒤 새 peer 연결로 정의하며 48회 확인했다. 여러 Acceptor를
동시에 묶는 multi-member partial failure는 이 API에 적용되지 않는다. 다만
`failedOnPeer()`가 구분하는 단일 원격 Acceptor의 CAP 완료 실패 주입은 아직 **NOT RUN**이다.
따라서 이 기록은 W03-05의 positive/cancel/reconnect 부분 PASS이며, 원격 완료 실패 callback을
검증하기 전까지 W03-05 전체와 M31-W03 전체는 **진행 중**이다. W02 설치본 ISO 11예제·11역할
증거는 변경하지 않았고 CI/CD는 조회하지 않았다.
