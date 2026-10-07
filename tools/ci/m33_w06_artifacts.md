# M33-W06 exact target artifact 준비 계획

> **현재 사용 범위 — 2026-10-07:** 기존 W06 자동 실행을 정리하고
> [검증 파이프라인 재설계](<../../00_Docs/02_빌드 설계/11_M33_W06_검증_파이프라인_재설계.md>)를 준비한다.
> 이 문서는 아직 유효한 **기존 도구의 명령·증거 계약 reference**이며 새 구현의 실행 지시가 아니다.
> 새 구조·short mode·축소 bundle은 미구현이다. 현재 상태는 [M33 인계](../../00_Docs/M33_HANDOFF.md)를 따른다.

> **2026-10-05 재개 정책:** 주 에이전트 1개로 순차 처리하며 하위 에이전트는 생성하지 않는다.
> 기존 Actions shard는 허용하되 로컬 무거운 build/HIL은 한 번에 하나만 실행한다.
> 사용자가 이전 로컬 작업 자료를 삭제했으므로 옛 clone/result/index 경로를 그대로 사용하지 않는다.
> 실제 source·미커밋 변경·도구·권한을 확인하고 필요한 동일 exact artifact를 새 root에 복구하거나 재생성한다.
> 현재 상태·원격 run과 자료 가용성은 [M33 인계](../../00_Docs/M33_HANDOFF.md)를 따른다.

> **2026-10-07:** 현재 checkout은 `D:\w06\src`, 모든 새 실행·증거·cache·임시는 `D:\w06` 아래다.
> C의 설치된 SDK/toolchain은 읽기 입력으로만 사용한다. 로컬 build는 `--max-workers 1`로 실행한다.
> runtime producer는 같은 root에서 build 역할별 완료 byte를 재검증해 재사용하고, 실패한 물리
> fixture chain은 새 append-only attempt에서 cleanup부터 실행한다. 완성 결과의 손상이나 SAFETY
> 실패는 자동 retry하지 않는다. `.build-stages`·`.runtime-stages`와 원본 command log를 함께 보존한다.

이 문서는 `tools/ci/m33_w06_artifacts.py`가 만드는 48개 campaign과 별도 3-role soak artifact root의
준비·검증 절차를 설명한다. 이 도구는 target을 flash하지 않으며 mass erase, unlock,
recover를 호출하지 않는다. NCS는 `v3.4.0`, Windows toolchain은 `dcbdc366a1`이다.
도구의 build 병렬 상한은 2개지만 이번 D 작업의 로컬 무거운 build/HIL은 1개로 제한한다.

W05 전체 build는 완료돼 있다. 아래 명령은 기존 W06 도구의 재현용 reference다. 도구는 plan 생성,
build-only 실행, exact index와 runtime-input template 생성, staging, 재검증까지 제공한다. 어떤
subcommand도 target flash, mass erase, unlock, recover를 호출하지 않는다.

## 1. clean exact plan 생성

다음 명령은 Core HEAD와 board submodule, NCS `nrf`/`zephyr`, toolchain bundle을 lock과 대조한다.
Core, board, `nrf`, `zephyr` 네 checkout 중 하나라도 추적되지 않은 파일을 포함해 working tree가
dirty이면 plan을 만들지 않는다. 같은 네 checkout의 revision과 porcelain-clean 상태는 build
시작 전, 실패 종료, 성공 종료 시점에 각각 다시 검증한다.

```text
python tools/ci/m33_w06_artifacts.py plan \
  --sdk-root C:/ncs/v3.4.0 \
  --toolchain-root C:/ncs/toolchains/dcbdc366a1/opt/zephyr-sdk \
  --revision <40자리-Core-HEAD> \
  --output <외부-새-경로>/m33-w06-artifact-plan.json
```

plan은 현재 `CAMPAIGNS` 개수와 각 runner의 `argparse` option을 다시 읽고 그 수를
`expected_campaign_count`로 고정한다. 현재 작업 tree는 48개 campaign을 그대로 유지하며,
campaign 141개 slot에 non-campaign soak 9개 slot을 더한 총 150개 input slot이다. 이 가운데
141개가 build 산출물이고 9개가 runtime input이다. soak 9개는 `peripheral`, `mixed`, `central`
각 역할의 `hex-*`, `*-config`, `build-record-*`이며
`tests/zephyr/m32_regression_soak_hil`의 세 exact scenario에서만 만든다. 각 target image에는 실제
`testcase.yaml` scenario, direct west CMake
selector 또는 Arduino sketch/profile이 연결된다. 예를 들어 IEEE 802.15.4/ESB와 coexistence의
각 phase는 서로 다른 scenario로 유지되며, combined CIS/BIS receiver는
`nucode.m31.iso_bis.receiver`로 결합된다.

## 2. exact S Arduino checkout 준비

Arduino build는 기존 사용자 sketchbook이나 과거 설치본을 사용하지 않는다. 다음 명령은 plan의
clean S를 외부 새 root의 `user/hardware/nucode/zephyr`에 local clone하고, S의 board gitlink를
현재 clean board checkout에서 별도 clone한다. checkout과 board가 plan revision이며 clean인지
확인한 뒤 격리된 data/downloads/user를 가리키는 `arduino-cli.yaml`을 만든다. source·SDK·toolchain
안쪽 경로, 기존 경로, symlink는 거부한다.

```text
python tools/ci/m33_w06_artifacts.py prepare-arduino \
  --plan <외부-새-경로>/m33-w06-artifact-plan.json \
  --output-root <외부-새-경로>/arduino
```

생성된 `<외부-새-경로>/arduino/arduino-cli.yaml`을 다음 build에 그대로 사용한다. 이 과정은
package index를 갱신하거나 SDK/source byte를 수정하지 않으며 network 설치가 필요 없다.

## 3. build 실행

W05 완료 뒤에만 다음 명령으로 plan의 `recipe`를 실행한다. `work-root`, index, runtime manifest는
모두 기존에 없어야 하며 source/SDK/toolchain 밖의 새 경로여야 한다.

`plan.source_delta`는 W05 ADB 204/204를 CS quiesce 변경 전 baseline으로만 기록한다.
따라서 공개 RasInitiator/RasReflector와 `p2_cs_initiator`/`p2_cs_reflector` 네 source의
현재 byte hash와 `q` quiesce 계약을 다시 검사하고, `m31_cs_ras` 및
`m33_cs_acl_radio_risk`의 네 Arduino image를 current-S clean source에서 새로 build해야 한다.
이 네 delta build가 없으면 W05 결과를 현재 source PASS로 승격할 수 없다.

```text
python tools/ci/m33_w06_artifacts.py build \
  --plan <외부-새-경로>/m33-w06-artifact-plan.json \
  --work-root <외부-새-경로>/work \
  --index-output <외부-새-경로>/m33-w06-build-index.json \
  --runtime-inputs-output <외부-새-경로>/m33-w06-runtime-inputs.json \
  --arduino-cli <arduino-cli.exe> \
  --arduino-config <외부-새-경로>/arduino/arduino-cli.yaml \
  --fqbn-prefix nucode:zephyr:nu54dk \
  --timeout-seconds 3600 \
  --max-workers 2
```

`--max-workers`는 서로 다른 output과 action별 cache를 쓰는 독립 action만 동시에 실행한다. 기본은
2이고 자원 과다 사용을 막기 위한 상한은 4다. 각 action 자체의 `--jobs` 상한 2는 그대로 유지된다.
모든 action은 서로 다른 `builds/*` 또는 `records/*`, `caches/<action-id>`, XDG/ccache/pip/Python/
temporary cache를 사용한다. Arduino도 별도 `--build-cache-path`와 downloads cache를 사용한다.
profile record는 자신의 west build가 끝난 뒤에만 실행된다. 한 batch가 실패하면 다음 batch나
dependent action을 시작하지 않고, 이미 시작한 action receipt만 plan ordinal 순서로 FAIL evidence에
기록하며 build index/runtime manifest는 만들지 않는다.

- `builder=run_zephyr_build.py`: 기존 `tools/ci/run_zephyr_build.py`를 사용하고 같은 group의
  scenario를 한 outdir에 모아 `--jobs 2` 이하로 실행한다.
  `ZephyrAppConfiguration_ROOT`의 repository-owned hook은 각 `APPLICATION_BINARY_DIR` 아래
  USER_CACHE_DIR와 toolchain capability database를 격리한다. SDK source나 cache 값을 합성하지 않는다.
  `--inline-logs`와 정상 종료한 실패 scratch의 안전 검사·이동으로 실패 build.log/twister.json도
  artifact에 보존한다. 비영 exit는 output 존재와 무관하게 FAIL이며 timeout/unsafe tree는 이동하지 않는다.
- `builder=west_direct`: testcase가 없는 M33 beacon/profile fixture를 새 build directory에서
  `west build -b nrf54l15dk/nrf54l15/cpuapp/nu54dk`로 빌드한다. plan의 `selector`를 그대로
  CMake argument로 전달한다.
- `builder=arduino-cli`: plan의 각 역할을 실제 client/server/initiator/reflector/negative fixture
  sketch에 따로 결합하고 fresh build path로 컴파일한다. 생성된 primary HEX,
  `.nu54-build.json`, 그 record가 가리키는 native `.config`를 함께 결합한다.
- `builder=m33_diagnostics.py`: controller/scan-request build-semantic route의 기존 외부 build
  root를 `--jobs 2` 이하로 준비한다.
- `build_tree` slot은 runner가 요구하는 canonical Twister/sysbuild directory 자체를 가리킨다.
  빈 directory를 성공 산출물로 만들지 않는다.

각 subprocess는 `shell=False`로 실행된다. command, timeout, exit code, stdout/stderr 원본 log와
각 SHA-256, action ordinal, dependency, isolated cache root가 index의 action receipt에 남는다.
하나라도 timeout, nonzero exit, output 누락 또는
부분 slot이면 build index를 만들지 않고 work root에 FAIL receipt만 남긴다. Core/board/NCS/
Zephyr/toolchain identity와 Core/board/`nrf`/`zephyr` porcelain-clean 상태는 전체 실행 전후와
실패 경로에서 다시 확인한다.

`.github/workflows/m33-w06-build-shards.yml`은 같은 build를 Windows 2025 runner 네 개로 나눈다.
`workflow_dispatch`와 `Dev-0.6.0-M33` push에서만 시작하며 checkout/setup/cache/upload/download
action과 Arduino CLI action은 M31과 같은 40자리 commit pin을 사용한다. plan job은 exact Core SHA,
W02~W05 prerequisite blocker가 없는 clean snapshot, board gitlink, NCS 3.4.0/Zephyr/toolchain lock을
확인하고 4-shard 계약을 고정한다. Twister group은
multi-scenario build-tree 의존을 유지하면서 group당 최대 네 partition으로 나눠 process 시작 비용을
제한한다. dependency로 연결된 west build와 profile record는 같은 shard에 두고, 각 component는
action jobs와 소유 slot 수를 결합한 추정 부하가 가장 작은 shard에 결정적으로 배치한다. 각 shard는
서로 다른 runner/work/output/cache를 사용하고 내부에서도
`--max-workers 2` action cache 격리를 유지한다.

각 shard artifact에는 build output, `.config` 같은 hidden file, raw stdout/stderr, portable 상대 경로,
action ordinal/dependency, slot kind/recipe SHA-256, file 또는 directory SHA-256과 immutable manifest가
함께 들어간다. aggregate job은 네 manifest를 merge하지 않은 별도 root로 내려받고 current source와
lock을 다시 확인한 뒤 action/slot 누락·중복·revision·recipe·content hash를 재검증한다. 마지막으로
production `validate_index`를 전체 141 build slot에 다시 적용하고 9 runtime slot은 모두
`NOT_PROVIDED`로 남긴다. aggregate 결과는 `status=BUILD_ONLY`, `functional_hil=NOT_RUN`,
`physical_campaigns=NOT_RUN`, `soak=NOT_RUN`이며 Actions build를 HIL PASS로 승격하지 않는다.

동일 계약을 로컬/자체 runner에서 나누어 실행할 때는 먼저 `shard-plan`, 각 격리 root에서
`build-shard`, 모든 package를 한 root 아래 내려받은 뒤 `aggregate-shards` 순서로 호출한다.
aggregate의 `m33-w06-ci-build-aggregate.json`은 총 150, build 141, runtime 9를 고정한다. 표준
단일 `build` 명령은 계속 지원되며 출력 index schema도 동일하다.

다운로드 후 로컬 `aggregate-shards`의 `--output`, `--index-output`, `--runtime-inputs-output`은
**모두 `--shards-root` 바로 아래의 서로 다른 새 파일**이어야 한다. 원격 control directory의
기존 JSON을 덮어쓰지 않고 download root에 `local-*` 이름을 사용한다. 별도 sibling output root는
허용되지 않는다. 2026-10-05의 실제 6867 build PASS·runtime FAIL과 재사용 경로는
[302번 인계](<../../00_Docs/04_검증 기록/302_M33_W06_빌드_통과와_runtime_중단_인계.md>)를 따른다.

## 4. current connection과 9개 runtime input 결합

build가 끝나면 도구가 다음 strict JSON을 원자 생성한다. `entries`는 plan의 buildable
`(campaign_id, name)`을 정확히 한 번 포함해야 한다. 일부만 채운 index와 여분 entry는 모두
거부된다.

```json
{
  "schema_version": 1,
  "kind": "m33_w06_build_index",
  "plan_sha256": "<plan contract_sha256>",
  "source": { "<plan source object>": "그대로 복사" },
  "entries": [
    {
      "campaign_id": "m32_power",
      "name": "hex-central",
      "path": "C:/exact-build/.../zephyr/zephyr.hex"
    }
  ]
}
```

`m33-w06-runtime-inputs.json`에는 build로 만들 수 없는 9개 입력을 `NOT_PROVIDED`와 null path로
남긴다. 이것은 PASS가 아니다. 세 보드가 연결된 실행 직전에 다음 read-only inventory를 새로
만든다. DAPLink에서 읽은 raw UID는 기록하지 않고 SHA-256, 현재 COM, MSD root만 기록한다.
세 보드는 probe hash 정렬 순으로 `board_1`~`board_3` 물리 slot에 결정적으로 배치된다.
schema v2 `campaign_bindings`는 plan의 48개 campaign 순서와 각 campaign의 논리 역할을 읽어
자동 생성하며, 한 campaign 안에서는 slot을 중복하지 않고 순차 campaign끼리는 같은 세 slot을
재사용한다. `m33_diagnostics_dtm`에는 별도 `third` 역할도 자동 추가한다. 이 파일은
`m33_regression_run.py`의 실제 `_board_inventory` validator를 통과해야만 기록된다.

```text
python tools/ci/m33_w06_artifacts.py board-inventory \
  --plan <외부-새-경로>/m33-w06-artifact-plan.json \
  --output <외부-새-경로>/m33-w06-board-inventory.json
```

PowerShell에서는 inventory와 index를 다음처럼 읽을 수 있다. 이 변수는 raw UID를 포함하지 않는다.

```powershell
$Inventory = Get-Content <외부-새-경로>/m33-w06-board-inventory.json -Raw | ConvertFrom-Json
$Index = Get-Content <외부-새-경로>/m33-w06-build-index.json -Raw | ConvertFrom-Json
$ClientProbe = $Inventory.physical_slots[0].probe_sha256
$PeerServerProbe = $Inventory.physical_slots[1].probe_sha256
$ThirdProbe = $Inventory.physical_slots[2].probe_sha256
function Get-W06Path([string]$Campaign, [string]$Name) {
    ($Index.entries | Where-Object { $_.campaign_id -eq $Campaign -and $_.name -eq $Name }).path
}
$ClientImage = Get-W06Path m31_bap_duplex client-image
$ClientConfig = Get-W06Path m31_bap_duplex client-config
$ServerImage = Get-W06Path m31_bap_duplex server-image
$ServerConfig = Get-W06Path m31_bap_duplex server-config
```

연결 상태를 고정한 뒤 BAP 두 역할을 한 번에 sector-program하여 두 slot이 공유할 수 있는 exact
flash record를 만든다. 이 명령은 chip/mass erase, unlock, recover를 사용하지 않는다.

```powershell
py -3 tests/hil/nu54dk/m31_audio_bap_native_pair_run.py `
  --client-probe-sha256 $ClientProbe `
  --server-probe-sha256 $PeerServerProbe `
  --client-image $ClientImage --client-config $ClientConfig `
  --server-image $ServerImage --server-config $ServerConfig `
  --core-revision <40자리-Core-HEAD> --source-clean --flash-only `
  --arduino-sink --arduino-duplex-pair --require-lc3 `
  --output <외부-새-경로>/bap-flash-record.json
```

같은 current connection에서 ecosystem과 third-idle fixture producer를 실행한다. plan-only가 아니라
실제 fixture를 만들 때만 아래 세 authorization flag와 `--execute`를 함께 사용한다. producer는
build index의 current-S profile image/record, sector programming/readback, third-board read-only audit을
결합하며 `runtime-producer.json`에는 hash-only identity만 남긴다.

```powershell
py -3 tests/hil/nu54dk/m33_w06_runtime_fixture.py `
  --plan <외부-새-경로>/m33-w06-artifact-plan.json `
  --build-index <외부-새-경로>/m33-w06-build-index.json `
  --sdk-root C:/ncs/v3.4.0 `
  --toolchain-root C:/ncs/toolchains/dcbdc366a1/opt/zephyr-sdk `
  --output <외부-새-경로>/runtime-fixtures `
  --client-probe-sha256 $ClientProbe `
  --peer-probe-sha256 $PeerServerProbe `
  --third-probe-sha256 $ThirdProbe `
  --execute --authorize-sector-program --authorize-software-reset --authorize-three-board-hil
```

마지막으로 다음 명령이 9개 slot을 모두 자동 결합한다.

```text
python tools/ci/m33_w06_artifacts.py bind-runtime \
  --plan <외부-새-경로>/m33-w06-artifact-plan.json \
  --index <외부-새-경로>/m33-w06-build-index.json \
  --generated-root <외부-새-경로>/runtime-generated \
  --client-flash-record <외부-새-경로>/bap-flash-record.json \
  --server-flash-record <외부-새-경로>/bap-flash-record.json \
  --runtime-producer <외부-새-경로>/runtime-fixtures/runtime-producer.json \
  --output <외부-새-경로>/m33-w06-runtime-inputs.bound.json
```

자동 결합은 다음 계약을 적용한다.

- `imgtool`과 `imgtool-python`은 plan의 고정 SDK/toolchain에서 찾는다.
- M30 trust key와 M32 Mesh key는 각각 모든 관련 sysbuild의 MCUboot `.config`에 기록된
  `CONFIG_BOOT_SIGNATURE_KEY_FILE`을 역추적한다. SDK key를 생성·수정·복사하지 않는다.
- M30 wrong key만 외부의 기존에 없는 `runtime-generated`에 고정 toolchain Python과 imgtool
  `keygen -t ecdsa-p256`으로 새로 만들며 trust/Mesh key byte와 다른지 확인한다.
- client/server flash record는 current-S image/config hash, `FLASH_PREPARED`, sector flash receipt,
  서로 다른 hashed probe를 확인한다. 두 역할이 함께 든 한 record를 두 slot에 결합할 수 있다.
- producer manifest는 exact 두 fixture의 절대 path와 SHA-256, current-S clean PASS를 포함해야 한다.
  각 fixture는 기존 runner의 전체 validator로 다시 검사한다.
- raw UID field가 runtime producer, fixture 또는 flash record에 있으면 결합을 거부한다. PEM byte와
  raw UID는 stdout이나 JSON에 기록하지 않는다.

## 5. build index와 artifact root

모든 build entry와 runtime input이 준비된 뒤 새 artifact root에 stage한다.

```text
python tools/ci/m33_w06_artifacts.py stage \
  --plan <외부-새-경로>/m33-w06-artifact-plan.json \
  --index <외부-새-경로>/m33-w06-build-index.json \
  --runtime-inputs <외부-새-경로>/m33-w06-runtime-inputs.bound.json \
  --artifact-root <존재하지-않는-새-경로>/artifacts
```

native runner는 HEX의 `parent.parent/nucode_arduino_core_build.yml`을 읽고 Arduino runner는
HEX 옆 `.nu54-build.json`을 읽는다. 따라서 HEX만 복사하면 provenance가 끊어진다. stage는
원본 exact build 위치를 가리키는 file/directory symlink를 만든다. Windows에서는 file symlink를
허용하도록 Developer Mode 또는 동등한 권한이 필요하다. 권한이 없으면 부분 root를 남기지 않고
실패하며, copy나 합성 build record로 우회하지 않는다.

soak image는 일반 native record 대신 image의 `parent.parent/m33_w06_build_record.json`과
image의 `parent/.config`를 사용한다. stage 전 검증은
`m32_regression_soak_run.py::validate_m33_build_record`를 직접 호출해 full Core/board/NCS/Zephyr
revision, 현재 Core/application/board source digest, firmware/CMake/prj.conf digest와 role을 다시
계산한다. 세 image/config/build-record 중 하나라도 다른 build에서 왔으면 stage하지 않는다.

## 6. 재검증

```text
python tools/ci/m33_w06_artifacts.py validate \
  --plan <외부-새-경로>/m33-w06-artifact-plan.json \
  --artifact-root <외부-새-경로>/artifacts
```

검증기는 다음을 fail-closed로 확인한다.

- plan의 48개 campaign, non-campaign 3-role soak와 현재 runner option이 같은지
- Core/board/NCS/Zephyr/toolchain revision이 plan과 같은지
- 모든 input slot이 있고 symlink target이 staging 때와 같은지
- Intel HEX checksum, image/build record/config byte hash가 같은지
- native source digest 또는 Arduino/profile source snapshot이 현재 clean source와 같은지
- 한 campaign의 서로 다른 역할·phase slot이 같은 HEX hash로 잘못 채워지지 않았는지
- config, revision, source, path 또는 부분 산출물 drift가 없는지

`fixture`, signing key, flash record처럼 target build가 직접 만들지 않는 input은 build index와
분리하되 runtime manifest에서 생략하지 않는다. 실제 입력이 아직 없다면 stage와 dispatch는
실패하며, 그 상태를 PASS로 승격하지 않는다.

## 7. 3보드 순차 campaign inventory

`m33_regression_run.py prepare-spec`에는 schema v2 `m33_board_inventory`를 사용한다. 36개 이상의
논리 역할마다 별도 보드를 요구하지 않고, `physical_slots`에 현재 연결된 보드를 최대 3개만
기록한다. 각 slot에는 raw probe UID가 아니라 소문자로 정규화한 UID의 SHA-256만 기록한다.
`board_id`, `daplink_uid`, `probe_uid` 같은 raw 식별자 필드는 허용되지 않는다.

전체 inventory 생성기는 현재 DAPLink의 USB serial hash·VID/PID와 interface x.3(APP) /
x.1(AUX)를 함께 확인한다. `port`와 `app`는 같은 target UART이며 `aux`는 동일 보드의 별도
VCOM이다. 세 보드의 여섯 COM이 모두 달라야 한다. 포트 누락·모호함·다른 보드의 AUX는
실기 전에 거부하며 과거 COM 번호를 복사하거나 같은 COM을 두 역할에 채우지 않는다.

`campaign_bindings`는 plan의 campaign 순서대로 각 논리 역할을 `physical_slots[].slot`에
결합한다. 서로 다른 campaign은 같은 slot을 재사용할 수 있지만, 하나의 campaign에서 동시에
쓰는 역할은 반드시 서로 다른 slot이어야 한다. DTM의 간섭용 `third` 역할도 같은 동시성 검사에
포함된다. 실행 spec과 receipt에는 역할별 probe SHA-256만 남는다. M30 runner도
`--probe-<role>-sha256`만 받으며, 내부 Python pyOCD backend가 live probe를 hash로 선택한다.
raw UID는 dispatcher argv, runner argv, 하위 pyOCD argv, native evidence, stdout/log 어디에도
기록하지 않는다. runner가 raw UID를 출력하면 log를 쓰기 전에 실행 전체를 거부한다.

아래 JSON은 binding 한 행만 보인 발췌 예시다. 실제 inventory의 `campaign_bindings`는 선택한
identifier plan의 물리 campaign을 plan 순서대로 빠짐없이 포함해야 한다.

```json
{
  "schema_version": 2,
  "kind": "m33_board_inventory",
  "source_revision": "<40자리-Core-HEAD>",
  "source_clean": true,
  "physical_slots": [
    {"slot": "board_1", "probe_sha256": "<sha256>", "port": "COM11", "app": "COM11", "aux": "COM14"},
    {"slot": "board_2", "probe_sha256": "<sha256>", "port": "COM12", "app": "COM12", "aux": "COM15"},
    {"slot": "board_3", "probe_sha256": "<sha256>", "port": "COM13", "app": "COM13", "aux": "COM16"}
  ],
  "campaign_bindings": [
    {
      "campaign_id": "m31_iso_cis",
      "roles": [
        {"role": "peer", "slot": "board_1"},
        {"role": "dut", "slot": "board_2"}
      ]
    }
  ]
}
```

`automatic_peers` spec은 더 이상 실행 전 `peer.<id>.result.json`을 요구하지 않는다. 등록된
scripted campaign 전부가 같은 dispatcher 실행에서 최소 20회 PASS한 뒤에만 인접
`peer_support_discovery` sidecar와 `peer_result`를 생성한다. 이것은 개발용 scripted peer 근거이며
Apple/Google 제품 또는 Ubuntu/macOS 실물 상호운용 PASS로 승격하지 않는다.

## 8. exact S 전체 실행 순서

W05가 완료되고 위 `plan → prepare-arduino → build → board-inventory → runtime input 결합 → stage
→ validate`가 모두 끝난 뒤에도 같은 40자리 Core HEAD와 clean 상태를 유지한다. 아래 `<bundle>`은
source checkout 밖에 미리 만든 하나의 directory다. 실행 순서는 바꾸지 않는다.

### 8.1 33+8+8 physical campaign

다음 명령 하나가 registry 삽입 순서대로 family 33개, resource 8개, automatic peer 8개 group을
각각 prepare한 뒤 즉시 실행한다. `m33-campaign-matrix.session.json`은 current S, board inventory의
byte hash, artifact/SDK/toolchain 경로, 49개 group 순서를 처음 실행 전에 고정한다. 각 실행은
`.campaign-attempts/campaign-group.<01..49>.<field>.<id>.attempt-<N>/` 아래에 spec·result와 native
sidecar를 append-only로 남긴다. 완료된 attempt는 actual receipt/child/native raw evidence까지 strict
재검증한 뒤 resume한다. 실패·부분 attempt는 덮어쓰거나 삭제하지 않고 같은 immutable session의 다음
번호에서 해당 group만 다시 실행한다. result만 있는 attempt, 번호 공백, 완료 attempt 뒤 추가 attempt,
session/input/hash drift는 다음 보드 동작 전에 거부한다. 49개가 모두 PASS해야 attempt 이력을 포함한
`m33-campaign-matrix.json`을 새로 만든다. source나 고정 입력이 바뀌면 새 output root를 사용한다.

```text
python tests/hil/nu54dk/m33_regression_run.py execute-matrix \
  --board-inventory <외부-새-경로>/m33-w06-board-inventory.json \
  --artifact-root <외부-새-경로>/artifacts \
  --output-root <bundle> \
  --sdk-root C:/ncs/v3.4.0 \
  --toolchain C:/ncs/toolchains/dcbdc366a1/opt/zephyr-sdk
```

이 명령은 각 등록 runner의 기존 명시 승인 인자만 사용한다. sector programming과 software reset은
runner 계약 범위에서만 수행하며 chip/mass erase, unlock, automatic recover는 허용하지 않는다.

### 8.2 별도 1,800초 3보드 soak

campaign matrix가 끝난 뒤 staged non-campaign soak image를 같은 세 물리 slot에 역할 순서대로
결합한다. production runner는 central START부터 세 역할 FINAL까지 host monotonic elapsed가 최소
1,800,000 ms인지 직접 검사한다. `<bundle>/m33-soak.json`과 모든 sidecar는 새 파일이어야 한다.

```powershell
$Inventory = Get-Content <외부-새-경로>/m33-w06-board-inventory.json -Raw | ConvertFrom-Json
$SoakPeripheral = '<외부-새-경로>/artifacts/m33_regression_soak/hex-peripheral'
$SoakMixed = '<외부-새-경로>/artifacts/m33_regression_soak/hex-mixed'
$SoakCentral = '<외부-새-경로>/artifacts/m33_regression_soak/hex-central'

py -3 tests/hil/nu54dk/m32_regression_soak_run.py `
  --probe-peripheral-sha256 $Inventory.physical_slots[0].probe_sha256 `
  --probe-mixed-sha256 $Inventory.physical_slots[1].probe_sha256 `
  --probe-central-sha256 $Inventory.physical_slots[2].probe_sha256 `
  --hex-peripheral $SoakPeripheral --hex-mixed $SoakMixed --hex-central $SoakCentral `
  --sdk-root C:/ncs/v3.4.0 `
  --output-prefix <bundle>/m33-soak
```

Windows HIL driver는 pyOCD 등 의존성이 설치된 현재 Python을 사용한다. Bundled Python을 직접
driver로 실행한 `ctypes` import 실패 이력과 내부 west의 고정 SDK/toolchain 환경은 구분한다.
NCS 3.4.0·toolchain pin은 그대로 유지한다.

### 8.3 Host regression을 기존 bundle에 추가

물리 campaign과 soak가 끝난 뒤 Host 회귀를 실행한다. 이 도구는 **63개 suite**를 각각 별도
subprocess로 실행하며, verbose test ID count/SHA-256 계약에는
`test_m33_w06_artifacts.py` 43개, `test_m33_w06_runtime_fixture.py` 15개,
`test_m33_execution.py` 21개, `test_m33_regression.py` 75개가 포함된다.
`test_build_matrix_runner.py` 11개와 `test_m33_profile_campaign.py` 4개를 포함한
GATT-cache source 10개·strict parser/실제 collector 16개를 포함한
전체 분모는 63-suite / 564-test이며
`<bundle>`의 기존 campaign/soak 파일은 보존한다.
Actions plan도 무거운 shard build 전에 48개 campaign의 argv/board binding과 49개 group의
prepare→validator, APP/AUX inventory의 source-only 회귀를 검사한다. 이 단위 회귀는 실제
보드 연결·image·runtime PASS가 아니며 로컬의 exact artifact 실기 전 점검을 대체하지 않는다.
반면 예정된 `result.json` 또는 63개 `*.log` 중 하나라도 이미 있으면 어떤 Host subprocess도
시작하기 전에 전체를 거부한다.

```text
python tools/bluetooth/m33_regression.py host --output <bundle>
```

### 8.4 SDK risk와 qualification 조사 evidence 생산

risk producer는 matrix manifest의 49개 actual group을 다시 검증하고 각 group의
`result → receipt → child → native` content-address 사슬에서만 일곱 JSON을 만든다. DTM noisy RF,
BIS controlled noisy RF, MCUboot active watchdog 조건이 실제로 실행되지 않았으면 각각
`CONDITION_NOT_MET`이며 PASS로 합성하지 않는다. 나머지 fixed PASS-only 위험도 대응 semantic과
native raw 구조가 함께 입증되지 않으면 producer 전체가 실패한다.

SDK risk JSON schema 2는 같은 campaign을 여러 group에서 독립 실행한 증거를 전부 보존한다.
`campaign_evidence`의 분모·순서는 campaign별 registry group 순서이며 각 receipt/child/native의
경로는 group 폴더가 아닌 `<bundle>` 기준이다. 서로 다른 nonce·receipt hash를 동일 실행으로
강제하거나 첫 실행만 선택하지 않는다. 모든 실행의 조건을 검사하며 첫 `CONDITION_NOT_MET` 뒤의
raw도 생략하지 않는다. schema 1의 단일 대표 실행을 schema 2로 편집해 승격하지 않는다.

Closure의 campaign 참조는 `.campaign-attempts/.../result.json` 같은 bundle 내부 하위 경로를
허용한다. Host/soak/risk/qualification sidecar는 기존 인접 파일 계약을 유지한다. 절대 경로,
`..`/별칭 경로, symlink·junction·reparse와 hash 변경은 거부하며 root 밖 파일을 복사해 맞추지 않는다.

```text
python tools/bluetooth/m33_regression.py risks \
  --campaign-matrix <bundle>/m33-campaign-matrix.json \
  --output <bundle>

python tools/bluetooth/m33_regression.py qualification \
  --output <bundle>/qualification.json
```

qualification producer는 Nordic nRF54L15의 고정 NCS 3.4.0 LTS 조사 결과만 기록한다. Host와
Controller는 `PLANNED_NO_DN`, Mesh는 `NOT_LISTED_NO_DN`, 세 component는
`EVIDENCE_RECORDED`다. 제품은 항상 `NOT_ASSESSED`이고 예제 PASS를 제품 qualification으로
승격하지 않는다.

### 8.5 closure 조립과 최종 재검증

matrix manifest를 사용하면 49개 `--campaign-evidence` 인자를 수동으로 다시 적지 않아도 된다.
일곱 risk 인자는 다음처럼 전부 명시한다.

```text
python tools/bluetooth/m33_regression.py assemble \
  --output <bundle>/closure.json \
  --host-regression <bundle>/result.json \
  --soak <bundle>/m33-soak.json \
  --campaign-matrix <bundle>/m33-campaign-matrix.json \
  --sdk-risk-evidence DRGN-29228=<bundle>/risk.DRGN-29228.json \
  --sdk-risk-evidence DRGN-29270=<bundle>/risk.DRGN-29270.json \
  --sdk-risk-evidence DRGN-29446=<bundle>/risk.DRGN-29446.json \
  --sdk-risk-evidence DRGN-29320=<bundle>/risk.DRGN-29320.json \
  --sdk-risk-evidence DRGN-29669=<bundle>/risk.DRGN-29669.json \
  --sdk-risk-evidence MESH_LPN_FRIEND_CLEAR=<bundle>/risk.MESH_LPN_FRIEND_CLEAR.json \
  --sdk-risk-evidence MCUBOOT_ACTIVE_WATCHDOG=<bundle>/risk.MCUBOOT_ACTIVE_WATCHDOG.json \
  --qualification-evidence <bundle>/qualification.json

python tools/bluetooth/m33_regression.py validate \
  --manifest <bundle>/closure.json
```

assembler와 validator는 새 시험을 실행하거나 PASS를 만들지 않는다. 같은 bundle의 SHA-256 byte,
current clean exact S, 33+8+8 actual group, 1,800초 soak, 63-suite Host, raw campaign에서 재도출한
7 SDK risk, 3 qualification 행만 검사한다. Apple/Google 제품 peer와 Windows/Ubuntu/macOS 실물
matrix는 `NOT_RUN`으로 보존한다. 누락·중복·부분 evidence, source/lock drift, 기존 output 덮어쓰기는
closure 파일을 쓰기 전에 거부한다.

### 8.6 비공개 원본과 공개 마감 기록

Template firmware에는 시험용 credential이 포함될 수 있으므로 전체 bundle을 저장소에 복사하지
않는다. D의 원본을 유지한 상태에서 strict closure를 먼저 통과시킨 뒤 새 외부 출력에 공개용
`closure-reference.json`, `bundle-files.json`, `.gitattributes` 세 파일만 내보낸다.

```powershell
py -3 tools/bluetooth/m33_regression.py export-closure `
  --manifest D:/w06/<run>/bundle/closure.json `
  --output D:/w06/<run>/public-closure
```

내보내기는 실제 시험이 아니라 `EVIDENCE_REFERENCED`다. 공개 index에는 source와 상대 경로·size·
SHA-256만 들어간다. 이 세 파일만 `00_Docs/04_검증 기록/evidence/m33-w06-<identity>`로 옮기고
readiness의 W06 package와 세 case가 같은 `closure-reference.json`을 가리키게 한다.
`.gitattributes`는 공개 metadata 자체의 checkout byte를 보존하므로 반드시 함께 기록한다.

마감 C는 검증 source S의 바로 다음 단일 non-merge 기록 commit이어야 한다. 현행 TODO·인계·
지원표·SDK 위험·qualification·303 계획과 `NNN_M33_W06_*완료.md`만 명시적 allowlist로 허용한다.
구현 변경, 동결 TODO, 옛 302 인계 또는 중간 commit을 끼운 임의 ancestor 승계는 거부한다.

```powershell
$env:NUCODE_M33_W06_EVIDENCE_ROOT = 'D:/w06/<run>/bundle'
py -3 tools/bluetooth/m33_contract.py --sdk-root C:/ncs/v3.4.0 --check
```

완료 검사는 지정한 실제 외부 bundle의 모든 파일과 공개 index를 대조한 뒤 기존 strict closure를
실행한다. metadata만 존재하거나 원본 누락·추가·변조·link·source drift가 있으면 실패한다.
원본을 옮길 때는 전체 bundle과 검증에 필요한 exact 입력을 함께 보존하고 환경 경로를 다시 지정한다.
원본 없이 공개 index만으로 물리 PASS를 재생성하지 않는다. HOST 이후 순서는 이 절차의 승인 범위가 아니다.
