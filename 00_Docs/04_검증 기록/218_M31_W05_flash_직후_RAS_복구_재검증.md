# M31-W05 flash 직후 RAS 복구 재검증

`013a1274fed9f66d226ebf08de4d4886255d97e5`의 clean source에서 공개
`RasInitiator`와 `RasReflector`를 다시 빌드했다. 실기 직전 현재 COM14/COM13 역할,
두 probe SHA-256, controller/SoC register와 두 HEX SHA-256을 다시 확인했다.
sector flash와 hardware reset만 사용했으며 unlock, recover, mass erase는 수행하지 않았다.

[실행 원본](evidence/m31-w05-ras-013a1274/pair-postflash-100-20-20.json)은
다음 범위를 확인한다.

| 판정 범위 | 결과 | 근거와 경계 |
| --- | --- | --- |
| exact image/source | PASS | clean core revision과 두 image SHA-256, 고정 NCS/Zephyr/board register 기록 |
| flash 직후 secure RAS | PASS | 추가 pair reset 뒤 raw procedure 100개를 31.625초에 수신 |
| stop/restart | PASS | 명시적 `s`/`r`과 양측 disabled/enabled, 새 raw 결과를 20/20 확인 |
| disconnect/reconnect | PASS | 명시적 `d`, 양측 disconnect, scan·secure L2·CS·raw 복구를 20/20 확인 |
| 최종 STOP | PASS | 마지막 procedure stop과 reflector disabled를 확인한 뒤 lease 반환 |
| raw RAS | PASS | local/peer step count 일치와 RTT/tone 원본 형식 100건 확인 |
| 정밀 거리 정확도 | NOT RUN | 출력은 비보정 RTT 추정이며 기준 거리·보정 장치가 없음 |
| wrong-key negative | NOT RUN | 잘못된 LTK/passkey를 주입하지 않음 |

과거 flash 직후 counter gap과 연결 중단은 이번 exact run에서 재현되지 않았다. 이번
PASS는 현재 image가 flash 직후에도 성공할 수 있음을 증명하지만, 간헐 실패의 단일
원인을 확정하거나 반복 재현성 분모를 닫지는 않는다. 이전 실패 원본은 그대로 유지한다.
W05는 wrong-key negative와 flash 전환 반복 분모가 남아 **진행 중**이다.

## 같은 image의 두 번째 flash 반복

후속 clean source `a4ff62fff9b78493dbbf941a3a189512ab4d2119`에서 두 공개 예제를
다시 빌드했다. image SHA-256은 첫 실행과 같았고, 현재 mapping과 register를 다시 읽은 뒤
[두 번째 실행 원본](evidence/m31-w05-ras-a4ff62ff/pair-postflash-repeat-100-20-20.json)을
별도로 생성했다. 이 실행도 flash·pair reset 직후 raw procedure 100개를 27.570초에
수신했고 stop/restart 20/20, disconnect/reconnect 20/20과 최종 STOP을 모두 PASS했다.
빌드의 전역 메모리는 initiator 232,399/262,144 byte(88%), reflector
220,839/262,144 byte(84%)여서 low-memory 경고가 발생했다. 이는 W05 기능 FAIL은 아니지만
W06 통합 자원 예산에서 반드시 다시 판정할 위험으로 남긴다.

따라서 동일 image의 독립적인 두 번의 flash 실행은 모두 성공했다. 과거 실패 원본은
보존하며, 두 번의 성공만으로 간헐 중단의 단일 원인을 확정하지 않는다. wrong-key
negative와 정밀 거리 정확도는 계속 `NOT RUN`이다.
