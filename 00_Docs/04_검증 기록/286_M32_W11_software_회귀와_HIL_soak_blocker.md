# M32-W11 software 회귀와 exact HIL closure 완료

> W11 완료 시점의 결과를 보존한다. 이어진 W12 감사와 M32 12/12 최종 마감은
> [287번 기록](287_M32_W12_정합성_감사와_후속_인계.md)을 따른다.

| 항목 | 결과 |
| --- | --- |
| 작업 | `M32-W11` 영향 범위 회귀·negative·세 보드 기능 HIL·유한 soak |
| exact source | `94f0254499858800b4ced38b1211746b3f2175f8`, clean |
| 고정 기준 | NCS `v3.4.0` (`99553055607b…`), Zephyr `bf801e4e3d19…` |
| current software/build | **PASS — native 62/62, exact SHA CI 8 job success·failed 0** |
| 이전 광범위 checkpoint | `a9cb4a6d…` Arduino 74/74·Host 1,689/1,689 PASS 보존 |
| exact family closure | **PASS — 12/12** |
| signed Mesh DFU | **PASS — 5회 × 두 target, 10/10** |
| 유한 soak | **PASS — 1,800초, link당 10,000 packet, 손실·손상·중복·단절 0** |
| 보드 접근 | **PASS — 세 보드 AHB debug enabled, exact preflight의 ERASEALL required=false** |
| W11 작업 판정 | **완료 — M32 11/12, W12 정합성 감사만 남음** |

## 1. software·build 기준선

Current exact source에서 W02~W10 native 역할·negative build **62/62**를 다시 빌드했다. failed·error는
0이며 41개 HIL index가 각각 하나의 역할 image와 current short revision `94f025449985`를 가리킨다.
M32 contract, readiness·closure unit 14개, 문서 477개와 inventory도 이 source에서 PASS했다.

GitHub Actions run
[`37070892326`](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/37070892326)은
같은 full SHA에서 8 job success, failed 0이다. 대표 build는 workflow 조건에 따라 skipped됐으며
실패로 계산하지 않는다. Native 결과와 workflow 입력은
[`native-build-62.json`](evidence/m32-w11-exact-94f02544/native-build-62.json),
[`native-build-testplan.json`](evidence/m32-w11-exact-94f02544/native-build-testplan.json),
[`native-build-twister.json`](evidence/m32-w11-exact-94f02544/native-build-twister.json),
[`workflow-dispatch.json`](evidence/m32-w11-exact-94f02544/workflow-dispatch.json)이 소유한다.

Arduino 74/74와 전체 Host 1,689/1,689는 이전 clean `a9cb4a6d…` checkpoint에서 얻은 광범위
회귀 결과다. 이번 `94f02544…`에서 다시 실행한 결과로 바꾸어 쓰지 않으며, boot/settings 수정 뒤
current exact native 62/62·관련 Host 120개와 M31 연관 4개·current SHA CI로 변경 영향 범위를
재검증했다.

## 2. exact 12-family HIL

`regression-manifest.json`의 12개 family와 14개 raw evidence를 strict closure가 검사했다.

| family | exact 결과 | 주요 분모 |
| --- | --- | --- |
| capability | **PASS** | baseline·extended 두 역할 묶음 |
| power/path | **PASS** | power control·path loss·negative |
| timing/feature | **PASS** | subrating·SCA·frame space·short interval |
| advertising | **PASS** | set/SID 600 packet·negative |
| privacy | **PASS** | A/B 각 20회, peer 200 packet·negative |
| EAD | **PASS** | 인증·replay·ciphertext/key/IV negative |
| Nordic extensions | **PASS** | LLPM·QoS·time sync·event·notification |
| Mesh base | **PASS** | 두 node, 500/500 ACK·negative |
| Mesh management | **PASS** | 10회·350/350 operation·negative |
| Mesh update | **PASS** | BLOB 10회 + signed MDFU 10/10 |
| standalone radio | **PASS** | IEEE 802.15.4·ESB 각 2,000 packet |
| coexistence | **PASS** | 세 내부 조합, protocol별 4,000 packet |

최종
[`regression-family-status.json`](evidence/m32-w11-exact-94f02544/regression-family-status.json)은
`status=PASS`, `source_clean=true`, full SHA 일치, `baseline_family_passed=12/12`를 기록했다.
`--development`는 사용하지 않았다.

Privacy 첫 실행은 identity_a가 20/20을 완료한 뒤 identity_b의 마지막 재연결이 290초 경계에
걸려 `session_timeout`으로 FAIL했다. 원본
[`privacy-attempt-1-fail.json`](evidence/m32-w11-exact-94f02544/privacy-attempt-1-fail.json)과
[`transcript`](evidence/m32-w11-exact-94f02544/privacy-attempt-1-fail.transcript.log)를 보존했다.
같은 clean SHA·같은 image의 허용된 1회 진단 재실행은 A/B 각 20/20, peer 200/200,
wrong identity·unauthorized peer·active list change 거부와 STOP을 PASS했다. 최종 판정은
[`privacy.json`](evidence/m32-w11-exact-94f02544/privacy.json)이 소유한다.

## 3. MCUboot·RRAM settings와 signed MDFU

Mesh BLOB/MDFU 역할은 app만 sector flash하면 `0x0`의 MCUboot가 없어서 부팅할 수 있었다. Current
runner는 MCUboot와 signed app을 reset 없이 순서대로 기록하고, nRF54L RRAM settings 영역
`0x174000..0x17CFFF` 36,864 byte를 `0xff`로 채운 뒤 9,216 word를 read-back 검증하고 마지막에
한 번만 reset한다. 일반 flash erase를 settings 삭제 증거로 오인하지 않는다.

BLOB은 client 10회·5,120 chunk, 두 target 각각 10회·2,560 chunk, suspend/resume, wrong key와
bad digest 거부, 세 역할 END·STOP을 PASS했다. Signed MDFU는 candidate version `2.0.0.0`,
5 iteration × 두 target **10/10**, rollback 9회, wrong key·wrong image·partial image 거부를
4,107.781초에 PASS했다. Candidate signed binary는 55,040 byte다.

Build hash·크기와 private key 비포함 판정은
[`signed-mdfu-build.json`](evidence/m32-w11-exact-94f02544/signed-mdfu-build.json), runtime은
[`mesh-mdfu.json`](evidence/m32-w11-exact-94f02544/mesh-mdfu.json), BLOB은
[`mesh-blob.json`](evidence/m32-w11-exact-94f02544/mesh-blob.json)이 소유한다. 서명 개인키와
임시 build tree는 증거에 포함하지 않았다.

## 4. 1,800초 soak

세 역할 유한 soak는 다음 분모를 exact source에서 다시 PASS했다.

| 역할 | link | sequence | loss / corrupt / duplicate / unexpected disconnect |
| --- | ---: | ---: | --- |
| peripheral | 1 | 10,000 | 0 / 0 / 0 / 0 |
| central | 1 | 10,000 | 0 / 0 / 0 / 0 |
| mixed | 2 | link당 10,000 | 0 / 0 / 0 / 0 |

recovery failure·drop도 0이고 최대 gap은 peripheral 201 ms, mixed 251 ms다. 세 역할 모두
cleanup·FINAL을 PASS했다. 원본은
[`soak.json`](evidence/m32-w11-exact-94f02544/soak.json)과 역할별 transcript가 소유한다.

## 5. 보드 접근과 승인 경계

세 CMSIS-DAP V2 probe는 exact 실행 전마다 SHA-256 identity로 선택했다. 원시 UID는 문서·명령·
evidence에 저장하지 않았다. 세 보드 모두 DP ID `0x6ba02477`, TARGETID `0x201c0289`, AHB-AP ID
`0x84770001`, CTRL-AP ID `0x32880000`, APPROTECT status `0x00000000`으로 AHB debug 접근이
열려 있었다.

사용자는 차단 진단 뒤 **CTRL-AP ERASEALL과 기존 flash 삭제를 명시적으로 승인**했다. 그러나 이번
`94f02544…` exact family·MDFU·soak의 모든 access preflight는 `eraseall_required=false`였으므로
ERASEALL·mass erase·recover·unlock을 실행하지 않았다. 과거 보호 상태와 승인 이력, 현재 접근 상태,
실제 파괴 동작 미실행을 서로 구분한다.

## 6. 판정과 후속

W11 필수 software/build, 12-family exact closure, signed MDFU와 1,800초 soak가 모두 PASS했다.
`M32-REG-01:primary`와 `M32-SOAK-01:primary`를 PASS로 승격하며 W11은 완료다. M32는
**11/12**이고 남은 작업은 W12 API·예제·증거·지원표·후속 인계 정합성 감사뿐이다.

전체 exact evidence는
[`m32-w11-exact-94f02544`](evidence/m32-w11-exact-94f02544)에 보존한다. 복사 전 57개 파일을
검사해 raw probe UID, 비정제 `uid`/`probe_id`, private-key 표식이 각각 0임을 확인했다.
