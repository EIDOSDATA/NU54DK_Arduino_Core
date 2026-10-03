# M32-W08 BLOB·signed MDFU 완료와 timeout 진단 이력

최종 결과는 **BLOB 10/10회·signed MDFU 5회 × 두 target 10/10 배포 PASS**다. BLOB 결과는 §2,
signed MDFU 마감은 [§8](#8-최종-clean-exact-pass와-w08-마감)에서 확인한다. §3~§7은 최종 성공에
앞선 실패·원인 진단·교정 이력이며, 당시 미완료 판정과 exact source를 그대로 보존한다.

## 1. 범위

2026-10-02 `Dev-0.6.0-M32`의 clean source
`40e4c46b83addefd7ae12cc0c2af1b24764c4356`에서 세 NU54DK를 다시 매핑하고,
CMSIS-DAP v2·sector flash·`auto_unlock=false`만 사용해 `M32-BLOB-01:traffic`과
`M32-MDFU-01:primary`를 순서대로 실행했다. 자동 mass erase·unlock·recover와 물리 결선 변경은
수행하지 않았다.

## 2. BLOB exact PASS

세 역할 모두 10/10회를 끝냈다. Client는 두 target에 5,120 chunk를 보냈고 target별 2,560
chunk를 받았다. 32,768-byte object, 128-byte chunk, suspend/resume, wrong AppKey 거부,
bad digest 거부, 정상 digest와 세 역할 `STOPPED cleanup=pass`를 모두 확인했다. 원본은
[`m32-blob-01.json`](<evidence/m32-w08-blob-40e4c46b-exact/m32-blob-01.json>)과
[`m32-blob-01.transcript.log`](<evidence/m32-w08-blob-40e4c46b-exact/m32-blob-01.transcript.log>)이다.
Transcript SHA-256은 `46b35756f4f9172613b70244e62c86eb9ed907b71a9b3fce49785a7dea0bc472`다.
과거 `8dcb033e…` FAIL 원본은 삭제하거나 소급 변경하지 않는다.

## 3. 첫 signed MDFU 시도 FAIL

외부 ECDSA P-256 key로 candidate와 Distributor·target A·target B를 같은 public key에 서명했고,
candidate signed BIN은 343,511 byte, SHA-256
`41567b611534ad763e48689a8f7f5c88455ec95dc69618a8a9f777ee6c5af599`였다. 실행은 1,800초 뒤
`DFU iteration 1 timeout`으로 끝났다. Timeout 직후 Distributor는 DFD transfer phase에 있었고,
두 target은 base `0.0.0+0` confirmed image로 응답했다. 두 target STOP은 cleanup PASS였으며,
Distributor는 active transfer 때문에 STOP에 응답하지 않아 CMSIS-DAP v2 under-reset 레지스터
조회로 종료했다.

세 보드의 DP IDCODE `0x6ba02477`, TARGETID `0xf0000f40`, AHB-AP IDR `0x84770001`,
CTRL-AP IDR `0x32880000`, APPROTECT `0`은 모두 정상이다. 실패·레지스터·정리 상태는
[`m32-mdfu-01-attempt1.json`](<evidence/m32-w08-mdfu-40e4c46b-timeout/m32-mdfu-01-attempt1.json>)에
원시 probe UID 없이 보존한다. 당시 runner는 실패 경로에서 transcript 저장 전에 반환했으므로,
존재하지 않는 transcript를 PASS 증거로 만들지 않는다.

## 4. 원인과 보강

기존 `partial_image` negative는 candidate보다 16 byte만 작은 343,495 byte를 먼저 보낸 뒤,
343,511-byte valid candidate를 다섯 번 더 보내도록 구성됐다. Candidate 자체도 Distributor와 같은
전체 Bluetooth Mesh stack을 포함했다. 따라서 고정 1,800초 안에 첫 iteration조차 끝낼 수 없는
시험 구조였고 보드 fault나 접근 보호 문제가 아니다.

보강은 다음과 같다.

- Candidate를 저장된 nonce·target 역할, MCUboot header, confirm, UART BOOT/APPLIED/STOP만 가진
  최소 signed oracle로 분리했다.
- Mesh profile은 `mesh.conf`로 분리해 Distributor와 두 base target에만 적용한다.
- Partial-image negative 전송은 4,096 byte로 제한하되 target의 full candidate digest 검사로
  거부를 계속 증명한다.
- Host 계약 23개, M32 contract, 최소 candidate와 Distributor sysbuild를 확인했다. Candidate
  application footprint는 RRAM 54,876 B, RAM 32,204 B로 줄었다.

이 보강 build는 dirty source의 compile 확인이며 실기 PASS가 아니다. 보강을 commit한 clean exact
source에서 네 image를 다시 서명·빌드하고 5회 × 두 target, 세 negative, 네 rollback, 마지막 target A
confirm·target B rollback과 세 역할 STOP을 모두 얻을 때까지 W08은 미완료다.

## 5. 최소 candidate clean 재시험의 Apply 확인 FAIL

후속 clean source `84ecd3dc74b9c1f8b838742c6d3cc85176d5ade2`에서 55,040-byte 최소
candidate로 다시 실행했다. Wrong-key·wrong-image·4,096-byte partial-image negative는 모두
거부됐지만 첫 valid 배포의 Apply 확인에서 Distributor가 실패했다. CMSIS-DAP v2로 Distributor
RAM을 halt/read/resume한 결과 두 target 모두 DFU phase `APPLYING`, BLOB timeout, 내부 오류였고
DFD phase는 `FAILED`였다. DP/AP와 APPROTECT는 세 보드 모두 정상이었다. 원본 수치는
[`m32-mdfu-01-attempt2.json`](<evidence/m32-w08-mdfu-84ecd3dc-apply-confirm-fail/m32-mdfu-01-attempt2.json>)에
raw probe UID 없이 보존한다.

고정 Zephyr DFU Server의 Apply 응답 완료 callback과 현재 wrapper를 대조하니 wrapper는 MCUboot
test upgrade만 예약하고 실제 재부팅하지 않았다. 따라서 Distributor의 confirmation query 시점에
target은 여전히 base image였고 candidate firmware identity를 찾을 수 없었다. 또한 최소 candidate는
의도적으로 Mesh composition을 포함하지 않으므로 metadata에서 적용 후 unprovision 효과를 선언해야
한다. 다음 보강은 Apply Status 전송 뒤 warm reboot, 변경된 composition hash, Zephyr가 정의한
unprovision target의 무응답 성공 판정, 실패 transcript 자동 보존과 10,800초 유한 상한을 함께 적용한다.
Dirty source의 Distributor·두 target sysbuild와 관련 Host 계약 15개는 PASS했지만, 이 결과를 실기
PASS로 승격하지 않는다.

## 6. 첫 iteration PASS 뒤 rollback state 복구 FAIL

Clean source `6c8fe51ee6812347478453eca3ddc04ac706ac6b`의 자동 증거 보존 runner로 다시
실행했다. 이번에는 두 target이 candidate `2.0.0+0`을 실제 부팅하고 UART APPLIED를 보고했으며,
Distributor도 iteration 1의 target 2/2 성공을 기록했다. 두 target은 hardware reset 뒤 confirmed
base `0.0.0+0`으로 rollback했다. 따라서 Apply 응답 뒤 재부팅과 unprovision 효과 판정 보강은 실제로
동작했다.

실패는 `NEXT iteration=2` 직후 발생했다. CMSIS-DAP v2 attach로 두 target을 halt/read/resume한
결과 rollback된 base의 DFU Server가 모두 effect `BT_MESH_DFU_EFFECT_UNPROV`, phase
`BT_MESH_DFU_PHASE_APPLYING`을 settings에서 복원한 상태였다. 최소 candidate는 Mesh stack이 없어
UART APPLIED 시 DFU Server settings를 정리할 수 없으므로, 다음 metadata/start를 이전 Apply 진행
중으로 거부했다. 자동 보존 원본은
[`m32-mdfu-01.json`](<evidence/m32-w08-mdfu-6c8fe51e-exact/m32-mdfu-01.json>)과
[`m32-mdfu-01.transcript.log`](<evidence/m32-w08-mdfu-6c8fe51e-exact/m32-mdfu-01.transcript.log>)이며,
transcript SHA-256은 `3be19f1d0212d4cfcb54877398b28a1320860434d37d77b5460892b493ca2235`다.

다음 보강은 confirmed base가 `APPLYING`으로 복귀한 경우에만 이를 MCUboot rollback 복구로 판정해
`bt_mesh_dfu_srv_applied()`로 persisted state를 idle로 정리한다. 초기 base의 idle state와
unconfirmed candidate에는 적용하지 않는다. 이 clean 재시험은 966.250초, mass erase/recover 없이
끝났으며 iteration 1 성공을 5회 완료로 확대하지 않는다.

## 7. 두 iteration PASS 뒤 HIL 세션 상한 진단

Clean source `861d628aeb2909b32895481d5110ba3bec17be09`의 네 이미지를 다시 빌드해 실행했다.
두 target은 iteration 1과 2에서 candidate `2.0.0+0` 부팅·APPLIED를 각각 보고했고, 두 번 모두
hardware reset 뒤 confirmed base `0.0.0+0`으로 rollback했다. 따라서 §6의 persisted
`APPLYING` 복구는 두 번째 배포까지 실제로 통과했다.

실행은 총 1,928.703초에 iteration 3의 BLOB block 6 전송 중 `stage=timeout`으로 끝났다. 실패 직후
CMSIS-DAP v2 attach·halt/read/resume으로 확인한 두 target은 모두 BLOB
`WAITING_FOR_CHUNK`, DFU `TRANSFER_ACTIVE`, block 6이었고 누락 bitmap은 각각
`e0ffffff`, `f0ffffff`였다. Distributor도 `BLOCK_SEND`, block 6이었다. 즉 전송 state machine은
진행 중이었고 보드 접근 보호·apply·rollback 결함이 아니다.

원인은 target firmware의 `session_timeout_ms = 1,800,000`이다. 전체 실행 시간에서 exact
sector flash·초기화 약 129초를 제외하면 START 뒤 정확히 1,800초에 자체 timeout이 발생했다.
Runner의 `--result-timeout` 기본값과 최댓값은 이미 10,800초이므로 firmware의 유한 세션 상한도
10,800,000 ms로 맞추고 Host 계약에서 두 값을 함께 고정한다. 실패 원본은
[`m32-mdfu-01.json`](<evidence/m32-w08-mdfu-861d628a-exact/m32-mdfu-01.json>)과
[`m32-mdfu-01.transcript.log`](<evidence/m32-w08-mdfu-861d628a-exact/m32-mdfu-01.transcript.log>)이며,
transcript SHA-256은 `687cccb21a7acd650ab2fdf331e247b158b4bd521dfcd3213e95b38977f50628`이다.
두 iteration 성공을 5회 완료로 확대하지 않으며, 새 clean revision에서만 최종 PASS를 판정한다.

## 8. 최종 clean exact PASS와 W08 마감

`session_timeout_ms = 10,800,000`과 Host 계약을 함께 고정한 clean source
`e0a1b7fd7885b79bbc8d8b575c63f5468c94c2a8`에서 candidate·Distributor·target A·target B를
다시 빌드하고 동일 외부 ECDSA P-256 public key로 검증했다. Candidate signed image는 55,040 byte,
SHA-256 `f9bd3aba9f94302da28e228e7b71792c15104dbc16d0da7740f14b2dbe71a806`이다.

실행은 4,041.781초에 정상 종료했고 5회 × 두 target, 총 10/10 Firmware Distribution을 PASS했다.
각 회차에서 두 target 모두 candidate `2.0.0+0`을 실제 부팅해 candidate boot 10회를 기록했다.
1~4회는 두 target 모두 rollback했고, 5회는 target A를 confirm하고 target B를 rollback해 rollback
총 9회와 confirmed target 1개를 확인했다. Wrong image·wrong key·4,096-byte partial image는 모두
거부됐고 세 역할 STOP/cleanup도 PASS했다. Exact sector flash만 사용했으며 mass erase·unlock·recover는
수행하지 않았다.

최종 원본은 [`m32-mdfu-01.json`](<evidence/m32-w08-mdfu-e0a1b7fd-exact/m32-mdfu-01.json>)과
[`m32-mdfu-01.transcript.log`](<evidence/m32-w08-mdfu-e0a1b7fd-exact/m32-mdfu-01.transcript.log>)이다.
Transcript SHA-256은 `28608ed0a0bce2151e64ae0b793f6927aa3a46caae729a99fa7e1d45a281661b`다.
§2 BLOB PASS와 이번 MDFU PASS를 묶은
[`w08-closure-audit.json`](<evidence/m32-w08-mdfu-e0a1b7fd-exact/w08-closure-audit.json>)으로
M32-W08을 완료한다. §3·§5~§7의 FAIL은 원인과 수정 경계를 증명하는 역사 원본으로 그대로 보존한다.
