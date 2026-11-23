# M33-W03 exact 증거

## 고정 입력

- 기능 source: `17182660f8c1c1f4a9f6773b13fcfa453f65e1fc`
- NCS: `99553055607b2e9885fbc80ccd11fa9da81c2df0` (v3.4.0)
- Zephyr: `bf801e4e3d19e1ffa76164346480cb7734dd2800`
- board submodule: `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`
- toolchain bundle: `dcbdc366a1`
- HIL source identity: `17182660f8c1c1f4a9f6773b13fcfa453f65e1fc7986aaa495d32373bf04969c67c9b07c111dc2e01548f5af8d1fd1a0fa41bfdc`

## 자동 검사 결과

| 분모 | 결과 | 근거 |
| --- | --- | --- |
| W03 Host unit/negative | 13/13 PASS | MSYS2 UCRT GCC/G++, `test_m33_ecosystem*.py` |
| 공개 Arduino 예제 | 2/2 PASS | AppleNotificationClient, AppleMediaClient |
| Native application template | 4/4 PASS | Fast Pair input, Fast Pair locator, EnOcean, MDS |
| 두 보드 scripted-peer HIL | 9/9 PASS | access 거부 1, ANCS/AMS 정상·malformed 2회 cycle, wrong nonce·잘못된 command |
| 시험 소유 bond 정리 | 2/2 PASS | client/peer 정확히 1개씩 삭제, 기존 항목 불변 |
| 전체 M33 Host 회귀 | 57/57 PASS | `test_m33*.py` |
| Readiness·예제 안내 / Markdown | 17/17 PASS / 489개 PASS | 계약·metadata·UTF-8·local link |

공개 예제 build log SHA-256은 각각 다음과 같다.

- AppleNotificationClient: `534a02020bf88ba488d33f84ce3994281a7f17fbfafbdcccea43455531106929`
  - ELF: `29e8843e2cc2ee7180d6e1e6bb4b9c8c0e1a52e9174a7d4e7fb3231e4ce862f7`
- AppleMediaClient: `ee6cb15bb1ff85d13034649708b3b0a86f81d61bbfc54c552793c3f8372f2f24`
  - ELF: `838e3c05562ec53c51498126af5124852c44768e473f01b1477494d2799aa199`

Native template의 저장소 포함 manifest는 실제 credential 원문을 포함하지 않고 test/production mode와
source·산출물 hash만 기록한다. 별도 build log hash는 다음과 같다.

- Fast Pair input: `f71b170ac2dc4b19d219e4283309cb88bddc83d74fff88462123e1bfa24d7c96`
- Fast Pair locator: `1fb073faf9e9a400e2c1141e65990d4bb2a05d34e6d314c58fda5b92338d2eb6`
- EnOcean: `2a01f1b86c331bb425c1e92e4b15b30fe44a45888474f53bea7707b4844f3a3e`
- MDS: `2fe5d96f383f631bdcf5cbb4a4787a5a9352b225edf98697f6cedb9f8472ba07`

HIL image와 build log는 다음으로 고정했다.

- client image: `1f8ee4dd4501927ba7514053031d21c6e23e9f2c0cc9c8ceada4eccec0221947`
- client ELF: `152b91441e6197666fde56dd4be7215fde968705f3d6aae7228d591ec53258a4`
- client build log: `3fe9bd4589f2d3c627e17cb04a8c11e67f696bbbc80c0b64087b78d689b15673`
- peer image: `c828a434df31d561bec70c306492ae1aa883b2c3b4752792c3c8f0fddee85cb0`
- peer ELF: `3be1d8871d3209a32e7c0daee3007e51db123e23913b5bc7ecaaadf5e2cff22c`
- peer build log: `92806995b42c5abc229aca503e8f4933c8048bfaeb7233c83e6c65a3e2e093cc`

원본 증거 hash는 `preflight-program.json` `cf0726f9…`, `fixture.json` `5da87eeb…`,
`result.json` `4326d536…`, `transcript.log` `ea20630f…`다. Probe 원문 UID는 저장하지 않았고 SHA-256
identity만 기록했다. client/peer만 sector write와 `auto_unlock=false`로 기록했고, 제3 보드는 프로그램·
reset·resume 없이 HALTED/RADIO idle/활성 DPPI route 0을 재확인했다. Mass erase, unlock, recover는
실행하지 않았다.

## 외부 후속 경계

실제 iOS/iPadOS ANCS·AMS, Android Fast Pair/Find Hub, EnOcean 장치, Memfault gateway/cloud,
macOS·Windows·Linux의 기능별 UX는 모두 사용자 후속 `NOT_RUN`이다. 자동 build와 합성 peer PASS를
제품 상호운용·인증·실물 I/O PASS로 승격하지 않는다. AuraConfig 원본은 nRF5340 Audio DK 전용이므로
NU54DK native route는 `NOT_APPLICABLE`이며, 기존 공개 Audio 예제는 대체 학습 경로일 뿐 동등 구현 주장이 아니다.
