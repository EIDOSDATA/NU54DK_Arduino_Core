# M29-W07 `08cc52d6…` EATT timeout 진단

이 디렉터리의 두 transcript는 exact `08cc52d627a0aa362c77320f6b35a86e7200b33b`
전체 runner가 Signed Write 20/20과 replay 거부를 통과한 뒤 EATT 부하 중 HCI reason
`0x08`로 끊긴 원본이다. 이 실패를 `M29-SIGN-01` 또는 `M29-EATT-01` PASS로 승격하지 않는다.

실패 직후 양쪽 CMSIS-DAP을 500 kHz로 연결해 다음 SRAM과 fault 상태를 읽고 다시 실행했다.

| 대상 | CFSR / HFSR | EATT 상태 | disconnect reason |
| --- | --- | --- | --- |
| central | `0 / 0` | production read/write `1/1`, sent `1000/739`, 반환 buffer `1739` | `8` |
| peripheral | `0 / 0` | production write `1`, received `1000/734` | `8` |

따라서 CPU fault, EATT 연결 실패, payload 시작 전 실패가 아니다. 기존 4-buffer 공유 window로
동일 image의 EATT만 격리 실행하면 bearer별 1,000 operation을 모두 통과했지만 204.859초가
걸렸다. Zephyr EATT host의 bearer별 pending-send 경계에 맞춰 HIL sender를 bearer마다 고정
1-buffer로 제한한 dirty diagnostic image는 같은 보드·bond에서 105.391초에 `2000/2000`,
payload 오류·deadlock·starvation 0으로 통과했다. 후속 clean exact commit의 전체 runner로만
최종 test ID를 판정한다.
