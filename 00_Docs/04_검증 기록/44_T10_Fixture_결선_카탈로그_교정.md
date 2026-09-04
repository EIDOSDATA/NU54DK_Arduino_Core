# T10 Fixture 결선 카탈로그 교정

| 항목 | 내용 |
| --- | --- |
| 최초 실행 source | `8ebf3cc577bf28abcd44fac557d2ae1a29ffa226` |
| Board gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| 회로도 SHA-256 | `7e959be6d8db5d31c55366bd118093727062588770772b226117dd3826798466` |
| 작성일 | 2026-09-05 |
| 결과 | Fixture catalog revision 1의 물리 커넥터 번호 오류 발견, revision 2로 교정. T10은 새 결선 확인 전까지 미완료 |

## 1. 최초 Fixture 101 실행

두 NU54DK의 `DETAILS.TXT`에서 서로 다른 CMSIS-DAP UID, nRF54L15 target과 양쪽 `3299 mV`를
확인했다. 사용자의 첫 역할 설명에 따라 `E:` 보드를 role 1 DUT, `D:` 보드를 role 2 peer로
묶고 clean `8ebf3cc`에서 `nucode.v04.pair_dut`와 `nucode.v04.pair_peer`를 새 `C:/v42`에
build-only 했다. 두 target은 경고·실패·오류 없이 2/2 통과했다.

Fixture 101 revision 1 확인서를 현재 source, board, 두 UID hash, 두 HEX hash에 묶은 뒤
`auto_unlock=false`, mass erase/recover 없음, controlled start로 실행했다. 첫 vector인
9600 bps, 8N1, flow control off, 1 byte에서 role 2가 ready 상태인 채 수신 완료로 진행하지
않아 실패했다. 양쪽 fixture disarm은 `[0]`으로 완료됐다.

사용자가 역할을 `D:` 보드 A/DUT, `E:` 보드 B/peer로 정정해 두 번째 확인서를 만들고 역할
image를 올바르게 바꾸어 다시 실행했다. 같은 첫 vector와 같은 role 2 상태
`[1, 1, 0, 0, 0, 1, 0, 0]`에서 실패했으며 양쪽 disarm은 다시 성공했다. 두 실행은 RTS/CTS를
구동하지 않은 첫 단방향 byte에서 멈췄으므로 알려진 P0 DAP CTS 납땜 이슈와 무관하다.

- [역할 반전 실행 FAIL JSON](evidence/8ebf3cc/fixture101-role-reversed-fail.json)
- [역할 반전 append-only journal](evidence/8ebf3cc/fixture101-role-reversed-fail.json.jsonl)
- [역할 교정 뒤 catalog r1 실행 FAIL JSON](evidence/8ebf3cc/fixture101-catalog-r1-fail.json)
- [역할 교정 뒤 append-only journal](evidence/8ebf3cc/fixture101-catalog-r1-fail.json.jsonl)

두 확인서도 같은 evidence 디렉터리에 보존한다. 이는 당시 사용자가 revision 1 표대로 결선했다고
확인한 기록이지, 잘못된 표의 전기적 정확성이나 기능 PASS를 뜻하지 않는다.

## 2. 근본 원인

Board gitlink가 가리키는 `NU54-DK Schematic.pdf`의 9페이지를 180 DPI로 렌더하고 커넥터
번호, net label과 실제 firmware GPIO route를 함께 다시 대조했다. Revision 1 catalog와 이를
검사하던 Host test의 수기 pin map이 같은 잘못된 번호를 공유하고 있었다.

| GPIO net | revision 1 표기 | 회로도 9페이지의 실제 핀 |
| --- | --- | --- |
| P1.7/P1.6/P1.5/P1.4 | P2-9/10/11/12 | P2-8/9/10/11 |
| P2.4/P2.5 | P2-17/19 | P2-16/18 |
| P0.0/P0.1 | P2-25/26 | P2-24/25 |
| P0.2/P0.3 | P4-4/5 | P4-5/6 |
| P2.0/P2.1/P2.2 | P4-19/20/21 | P4-20/21/22 |
| P1.10/P1.14 | P4-8/12 | P4-9/13 |

따라서 revision 1 Fixture 101의 `DUT P4-21(P2.2) → peer P2-11(P1.5)` 선은 실제로
P2.1과 P1.4를 연결했다. Firmware는 올바른 GPIO net인 P2.2와 P1.5를 사용했으므로 물리 선과
만나지 않아 수신이 0 byte로 남았다. 더 위험하게 revision 1의 P0.1용 `P2-26`은 실제
`SWDCLK`다. 발견 즉시 추가 외부 시험을 중단하고 사용자에게 두 USB 분리를 요청했다.

## 3. 교정과 재발 방지

`v04_fixtures.json`의 UART 101~103, SPI 201~203, TWI 301, analog 401~404/408,
QDEC 420, I2S 430과 PDM 440의 모든 물리 connector 번호를 회로도 9페이지 기준으로
교정하고 catalog revision을 2로 올렸다. GPIO net, firmware pin route와 시험 vector 자체는
바꾸지 않았다. HIL README의 사람이 읽는 connector 표도 같은 값으로 맞췄다.

Catalog에 회로도 PDF SHA-256을 추가했다. `v04_fixture.py`는 실제 PDF byte가 이 hash와 다르면
preflight 단계에서 거부한다. Confirmation과 evidence에도 같은 hash를 포함하며, Host test는
회로도 hash, revision 2 connector map과 SWD/P2.6~P2.10 위험 물리 핀 미사용을 검사한다.
수정 중 관련 Host 29개와 M12 Host 전체, Markdown UTF-8/local-link gate가 통과했다.

## 4. 현재 판정과 다음 행동

- Revision 1 확인서와 두 FAIL은 역사 증거로 보존하며 PASS로 바꾸지 않는다.
- T08의 잘못된 결선표 완료 판정은 revision 2 교정·검사로 대체한다.
- T10과 T11은 여전히 미완료다. Revision 2 source를 clean commit으로 고정하고 exact role image를
  다시 build한 뒤, 전원 분리 상태에서 Fixture 101을 새 표대로 재결선해야 한다.
- 새 확인은 `D:` 보드 A/DUT와 `E:` 보드 B/peer, catalog revision 2, 새 source/HEX hash에
  다시 묶는다. 옛 확인서의 boolean이나 시각은 재사용하지 않는다.

