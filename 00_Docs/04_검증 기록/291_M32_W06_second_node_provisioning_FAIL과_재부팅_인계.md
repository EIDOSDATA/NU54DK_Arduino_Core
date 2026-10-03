# M32-W06 두 번째 node provisioning 원인 교정과 재개 인계

> **과거 중단·인계 기록:** 아래 정지 지시는 2026-09-30 당시 상태다. W06은 후속 exact HIL에서
> 두 node 구성·500/500 ACK·negative·STOP을 완료했으며
> [281번 기록](281_M32_W06_Mesh_기반_software와_HIL_blocker.md)에 최종 근거가 있다.
> 현재 개발 출발점은 [HANDOFF](../HANDOFF.md)를 따른다.

## 1. 정지 상태

2026-09-30 사용자 지시에 따라 M32 작업은 **W06에서 정지**한다. W01~W05와 W09는
완료 상태이고 전체 완료 분자는 **6/12**다. W06 software·Host 회귀·세 역할 image build는
완료했지만 exact HIL이 FAIL이므로 W06은 완료로 계산하지 않는다. W07 이후 실기는 이번
작업에서 진행하지 않았다.

| 항목 | 정지 시점 상태 |
| --- | --- |
| branch | `Dev-0.6.0-M32` |
| 마지막 실기 image source | `70a687698bdd293ae53a8cec52ca114f918a6bb4` |
| 현재 source | `2b9dfce2d06d62f5db76886d8359e6f148d0c8e4` |
| Host | M32 98/98, capability 포함 선택 검사 52/52 PASS |
| image build | provisioner·node A·node B 3/3 PASS |
| probe | 세 장치 모두 CMSIS-DAP v2 DP/AP PASS, sector flash 사용 |
| exact HIL | provisioning-only PASS — 두 remote node 모두 완료, 전체 분모 미실행 |

`70a687698bdd…`에서 CDB node count를 2에서 3으로 교정했고, 짧은 세 보드 확인에서
provisioner·node A·node B 모두 `provisioned=1`을 확인했다. 아래 FAIL은 교정 전 이력이며
전체 500-message·negative HIL은 아직 미완료다. `2b9dfce2d06d…`에서는 W06 최소 HIL
profile과 공개 Arduino provisioner의 확장 용량 profile을 분리했다.

## 2. 마지막 관측

마지막 실행은 첫 node provisioning 뒤 두 번째 node에 대해 PB-ADV link를 반복해서 열고
닫았지만 provisioning 완료 callback에 도달하지 못했다. 종료 시 계수는
`provision_attempts=56`, `links_opened=55`, `links_closed=55`, `added=1`,
`configured=0`, `sent=0`, `acknowledged=0`이다.

E와 G의 node 역할을 교환해도 항상 첫 node 역할은 성공하고 두 번째 node 역할이 실패했다.
따라서 E drive 또는 특정 물리 보드 문제로 분류하지 않는다. stack overflow 두 건은 앞선
revision에서 교정됐으며 마지막 실행에는 stack/fault가 없었다.

## 3. 보존 로그

- 결과 JSON: [`m32-mesh-06-role-swap.json`](<evidence/m32-w06-exact-6af305d3/m32-mesh-06-role-swap.json>)
- UART transcript: [`m32-mesh-06-role-swap.transcript.log`](<evidence/m32-w06-exact-6af305d3/m32-mesh-06-role-swap.transcript.log>)
- 전체 W06 이력: [`281_M32_W06_Mesh_기반_software와_HIL_blocker.md`](<281_M32_W06_Mesh_기반_software와_HIL_blocker.md>)

로그에는 probe raw UID를 남기지 않았고 SHA-256 mapping만 기록했다.

## 4. 재개 뒤 첫 작업

1. 세 장치의 drive·COM·CMSIS-DAP v2 DP/AP identity를 다시 확인한다.
2. `2b9dfce2d06d…`에서 세 역할 image를 다시 빌드하고 configuration 진행 상태를 짧게 계측한다.
3. configuration이 완료되면 300 base + 200 secured message와 negative·STOP을 실행해
   `M32-MESH-01`·`M32-MESHSEC-01`을 판정한다.
4. W06 전체 PASS가 되기 전에는 W07 exact HIL로 넘어가지 않는다.
