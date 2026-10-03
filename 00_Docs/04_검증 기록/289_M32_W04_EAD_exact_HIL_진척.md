# M32-W04 EAD exact HIL 진척

> **단계별 진행 기록:** 아래 EAD 판정과 M32 3/12는 이 실행 당시 상태다. 후속 ADV·PRIV와
> W04 전체 완료는 [290번 기록](290_M32_W04_광고_identity_privacy_exact_HIL_완료.md)을 따른다.

## 1. 판정

| 항목 | 결과 |
| --- | --- |
| exact source | `4af5b15a54aacc9d15f8257e535bbd7bc635b78b` |
| 고정 환경 | board `fe65f2f0880b…`, NCS `99553055607b…`, Zephyr `bf801e4e3d19…` |
| probe 경로 | **CMSIS-DAP v2**, 500 kHz, under-reset, `auto_unlock=false` |
| target build | advertiser/scanner **2/2 PASS** |
| `M32-EAD-01:primary` | **PASS** |
| W04 전체 | **진행 — ADV·PRIV 두 세 보드 시험 대기** |
| M32 완료 수 | **3/12 유지** |

CMSIS-DAP v2로 F/G 두 보드의 DP/AP identity와 비보호 상태를 확인한 뒤 sector flash와 별도
hardware reset을 수행했다. 자동 unlock·recover·mass erase는 사용하지 않았다. 두 image는 같은
exact Core revision을 UART protocol에 보고했고 역할별 STOP까지 완료했다.

## 2. EAD 결과

| 분모 | 결과 |
| --- | ---: |
| advertising payload update | 20/20 |
| raw EAD report | 400/400 |
| unique authenticated sequence | 20/20 |
| replay 거부 | 20/20 |
| ciphertext 변조 거부 | 20/20 |
| 잘못된 session key 거부 | 20/20 |
| 잘못된 IV 거부 | 20/20 |
| scan queue drop | 0 |
| callback main-thread 판정 | 2/2 PASS |
| bounded STOP | 2/2 PASS |

광고자는 sequence마다 새 randomizer를 사용했고 scanner는 exact nonce가 포함된 plaintext만
인증했다. 첫 인증 직후 같은 ciphertext의 replay, MIC를 바꾼 ciphertext, 잘못된 key와 잘못된 IV를
각각 독립 객체로 거부했다. 허용 손실 4개보다 엄격한 loss 0으로 packet 분모를 충족했다.

## 3. CMSIS-DAP v2 복구 경계

세 probe 모두 USB에서 CMSIS-DAP v2로 열거된다. E probe는 attach 질의에서 한때 `No ACK`였으나
500 kHz under-reset 비파괴 DP/AP 질의에서 정상 identity로 복귀했다. E/F/G 모두 DP
`0x6ba02477`, AHB-AP `0x84770001`, CTRL-AP `0x32880000`, APPROTECT status 0을 확인했다.
이 관측은 다음 세 보드 시험을 재개할 수 있다는 장비 preflight이며 아직 ADV·PRIV PASS 자체는 아니다.

## 4. 증거와 남은 범위

- build: [`native-build-summary.json`](evidence/m32-w04-exact-4af5b15a/native-build-summary.json)
- EAD envelope: [`m32-ead-01.json`](evidence/m32-w04-exact-4af5b15a/m32-ead-01.json)
- UART 원본: [`m32-ead-01.transcript.log`](evidence/m32-w04-exact-4af5b15a/m32-ead-01.transcript.log)
- 진행 감사: [`w04-progress-audit.json`](evidence/m32-w04-exact-4af5b15a/w04-progress-audit.json)

`M32-ADV-01:primary`의 set/SID 600 packet·세 negative와 `M32-PRIV-01:primary`의 identity/list
재연결 200 packet·세 negative를 같은 v2 안전 경로로 완료해야 W04를 완료로 승격한다.
