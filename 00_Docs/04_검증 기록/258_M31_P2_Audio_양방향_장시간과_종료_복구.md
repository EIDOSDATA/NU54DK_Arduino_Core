# 258 — M31 P2 Audio/ISO 양방향 장시간·종료 경합

> 현재 판정(2026-09-25): P2 세 기술 축은 [262번](262_M31_메모리_최적화_P2_세_축_완료.md)에서 완료됐다.
> 아래의 미완료·HOLD·다음 작업 문구는 이 기록 작성 당시 상태이며 원본 판정을 보존한다.

## 판정과 수정

두 exact NU54DK에서 공개 `BapUnicastDuplexClient`와
`BapUnicastDuplexServer`의 본문을 byte 동일하게 staging해 P2 메모리
계측 wrapper로 실행했다. 재현용
[`stage_p2_audio_duplex.py`](../../tests/arduino-cli/stage_p2_audio_duplex.py)는
원본 SHA-256을 manifest에 기록한다. probe UID·app/aux COM·HEX hash를
확인한 뒤 지정한 두 보드만 자동 unlock 없는 sector flash로 갱신했다.

최초 10,000-frame 양방향 실행은 양쪽 전송·복호화 목표와 drop 0까지
도달했지만 client 종료 직후 server `bt_bap_stream_send()`가
`-ENOTCONN`(`native=-128`)을 반환했다. 기존 `sendFrame()`은 이를 일반
`stack_error`로만 처리해 이미 끊어진 source를 streaming으로 남겼다.
[실패 원본](evidence/m31-p2-four-axes-20260925/audio-duplex-10000-before-fix.json)을
보존하고, 해당 반환에서 source streaming을 즉시 해제해 `not_ready`로
분류하도록 수정했다. 연결이 살아 있는 오류까지 숨기지 않는다.
첫 실패 실행은 client STOP만 관찰했고 server STOP은 관찰하지 못했다.
당시 실행기의 cleanup도 이미 기록된 오류를 다시 예외로 처리해 종료 명령을
끝까지 기다리지 못했다. 이 판정기 경합을 수정했지만 첫 원본의 STOP을
사후 성공으로 바꾸지 않는다.

수정 server와 같은 client image로 재실행한 결과, 양방향 각각 송신·복호화
**10,000 frame 이상, decode drop 0, 양측 STOP**을 확인했다.
[성공 원본](evidence/m31-p2-four-axes-20260925/audio-duplex-10000-after-fix.json)의
STOP high-water는 다음과 같다. 수치는 `used/reserved B`다.

| 관찰 항목 | client | server |
| --- | ---: | ---: |
| BT RX WQ | 1,520/3,200 | 1,232/3,200 |
| BT LW WQ | 936/2,104 | 1,168/2,104 |
| MPSL Work | 400/1,024 | 656/1,024 |
| main | 3,568/8,192 | 3,560/8,192 |
| libc malloc allocated/peak | 0/0 | 0/0 |

client HEX SHA-256은
`03017b5adc874e0c4051ab227adcc902a32e56dd701938e60e82ea32c7419b99`,
수정 server는
`617e82b6e2fd45adc20b3c635544b7ffd7172c53c7c84ff39ca850f78021fdba`다.
client 정적 FLASH/RAM은 `349,992/74,546 B`, 수정 server는
`331,024/72,116 B`다. 이어서 같은 양방향 image로 각 100 frame 전송·
복호화 뒤 즉시 종료하는 독립 실행을 20회 반복했고 모두 양측 STOP·drop 0으로
PASS했다. [반복 실행 원본](evidence/m31-p2-four-axes-20260925/)도 보존한다.

원본 공개 예제 loop가 UART 종료 문자를 먼저 소비할 수 있어 실행기는 `x`를
유한 간격으로 재전송한다. 실패 cleanup에서는 이미 기록된 오류를 지우지
않으면서 STOP을 끝까지 시도한다. 이 결과는 단일 양방향 CIS의 장시간·
종료 경합에 한정한다. 남은 Audio 부하는 **지원 용량의 다중 stream·암호화 오류와
그때의 stack/heap 여유**이며 [M31 TODO](../TODO_M31.md)의 세 축 안에서 판정한다.
물리 전원 차단·모든 조합을 자동 추가하지 않는다. SDC 내부 high-water 비노출은
추가 gate가 아니며 SDK 요구량·정렬을 유지한다. 이번 정상 부하만으로 stack을 줄이지 않는다.
