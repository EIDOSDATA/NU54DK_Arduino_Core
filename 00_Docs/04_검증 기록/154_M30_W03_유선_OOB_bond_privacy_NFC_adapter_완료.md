# M30-W03 유선 OOB·bond/privacy·NFC adapter 완료

## 결과

M30-W03을 고정 board `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`, NCS v3.4.0에서
완료했다. 유선 USB/DAPLink VCOM으로 LE Secure Connections OOB를 20회 수행했고, 별도의
bond/privacy 시험에서 schema migration, RPA 회전 3회, 새 pairing 없는 bonded reconnect 20회와
stale key 거부를 확인했다. NFC adapter는 같은 canonical OOB record의 NDEF encode/decode와 두
target image build까지만 검증했으며, 사용자 범위 결정대로 NFC RF는 `NOT RUN`이다.

| Gate | 결과 |
| --- | --- |
| W03 Host 계약·parser | **13/13 PASS** |
| OOB peripheral/central target | **2/2 PASS, warning 0** |
| 실제 `M30-OOB-01` | **wired 20/20, MITM 20/20, mismatch accept 0** |
| BOND peripheral/central target | **2/2 PASS, warning 0** |
| 실제 `M30-BOND-01` | **reconnect 20/20, RPA rotation 3, migration 1, stale accept 0** |
| NFC adapter | **Host/target build PASS, RF `NOT RUN`** |
| M30 진행률 | **W03 완료, 작업 묶음 3/8·test ID 4/10 PASS** |

## 구현 경계

- OOB record는 local/remote address, Secure Connections confirm/random과 CRC-32를 포함하며 최대
  192 byte다. 두 link slot은 generation handle과 exact peer 주소로 결합되고 mismatch·CRC 오류를
  fail-closed로 거부한다.
- 유선 carrier는 Host가 두 DAPLink VCOM 사이에서 canonical frame을 전달한다. transcript에는 raw
  OOB material 대신 SHA-256만 보존한다.
- NFC adapter는 opt-in `CONFIG_NUCODE_BLE_NFC_OOB_ADAPTER`에서 단일 Bluetooth LE OOB MIME NDEF
  record를 encode/decode한다. NFCT driver나 antenna를 직접 소유하지 않으며 기본값은 OFF다.
- bond metadata는 resolved identity, 16-byte SC key, security level, OOB flag와 database revision을
  고정 네 slot에 저장한다. 구형 schema-1 record는 첫 restored identity link에서 schema 2로
  이행하며, future·손상·고아 metadata는 거부한다.
- privacy 회전은 송신측 extended advertising set의 `rpa_expired` event를 세 번 관측하고 각 만료
  뒤 stop/start로 새 주소를 적용했다. 본딩된 central의 scan callback 주소는 stack에서 identity로
  resolve되므로 이를 온에어 RPA 원본으로 오판하지 않는다.

## 실제 결과와 증적

### M30-OOB-01

Exact Core `284254c7176fa0bf996137567952ae9d0ce5b4c0`의 두 역할 image로 68.182초 동안
유선 OOB pairing 20회와 L4/MITM link 20회를 완료했다. 변조 frame 수락은 0이고 NFC RF 실행은
0회다.

- [OOB 구조화 evidence](evidence/m30-w03-284254c7-oob/m30-oob-evidence.json)
- [OOB peripheral transcript](evidence/m30-w03-284254c7-oob/m30-oob-evidence.peripheral.transcript.log)
- [OOB central transcript](evidence/m30-w03-284254c7-oob/m30-oob-evidence.central.transcript.log)

### M30-BOND-01

Exact Core `83a4d11a20e6d16ed0db56382c20133f448cff91`의 두 역할 image로 56.059초 동안
schema-1 저장과 warm reboot, metadata migration 1회, 광고측 RPA 회전 3회와 bonded reconnect
20회를 완료했다. migration 뒤 새 pairing은 0이고 peripheral에서 bond를 지운 뒤 central의 stale
key 수락도 0이다.

- [BOND 구조화 evidence](evidence/m30-w03-83a4d11a-bond/m30-bond-evidence.json)
- [BOND peripheral transcript](evidence/m30-w03-83a4d11a-bond/m30-bond-evidence.peripheral.transcript.log)
- [BOND central transcript](evidence/m30-w03-83a4d11a-bond/m30-bond-evidence.central.transcript.log)

두 증적 모두 raw probe UID 대신 SHA-256만 포함한다. raw OOB frame, confirm/random, passkey와
`Unique ID`가 transcript에 없음을 검사했다. sector flash만 사용했고 mass erase/recover와 실제 전원
차단은 수행하지 않았다. BOND의 네 번 재부팅은 모두 warm reboot이며 power-loss 증거가 아니다.

## 실패 분류와 수정

- OOB central이 전달받은 remote RPA와 실제 scan 주소를 결합하지 못해 연결 전에 정확한 peer를
  찾지 못했다. scan-time remote address binding을 추가했다.
- Zephyr legacy advertiser 시작이 기존 RPA valid 상태를 지우므로, 광고 시작 뒤 local OOB를 생성해
  frame 주소와 실제 광고 주소를 일치시켰다.
- `bt_le_oob_set_sc_data()`가 pairing 동안 포인터를 보존하는데 stack-local 구조체를 넘기던 production
  수명주기 결함을 발견했다. 두 OOB slot에 native local/remote 구조체를 영속 보관하도록 수정했다.
- BOND fixture가 부팅 직후 metadata migration을 기대했지만 production은 첫 identity 연결에서 startup
  bond snapshot과 migration을 수행한다. READY/START는 0, restored link 최종 결과는 1로 계약을
  교정했다.
- 본딩 뒤 central scan callback에는 RPA가 아니라 resolved identity가 전달됐다. 광고측 extended set의
  만료 event로 회전 관측을 옮기고 필요한 Kconfig를 명시했다.
- 실패 시 transcript가 남지 않아 진단이 지연되는 문제를 고쳐, 이후 러너는 승인된 protocol 진행을
  실시간 출력하고 실패 transcript를 보존한다.

각 수정 뒤 exact source로 두 역할을 다시 빌드하고 전체 해당 시험을 처음부터 재실행했다. 무한
재시도, reset을 이용한 전원 시험 대체, mass erase/recover는 사용하지 않았다.

## 다음 작업

M30은 **3/8 작업 묶음, 4/10 test ID PASS**다. 다음은 M30-W04로 기존 BAS/DIS/HID keyboard를
회귀하면서 HID mouse, consumer control, HRS와 ESS를 추가해 catalog 7개와 서비스별 100 operation을
두 보드에서 검증한다. 실제 target USB 전원 차단은 W07 통합 HIL과 `M30-POWER-01` 준비가 끝난 뒤,
W08 주입 직전에만 요청한다.
