# 정책 원본과 생성물

하드웨어 사실은 고정 NCS DTS와 board submodule이 소유한다. 제품 JSON은 허용 route,
공개 singleton, 구현·build·실기 상태를 소유한다. 생성 C++/Markdown은 원본을 직접
대신하지 않는다. 기존 schema와 validator의 독립 기대값·부정 시험을 유지한다.

| 원본 | 생성기 / 생성물 | 독립 계약 |
| --- | --- | --- |
| [peripheral-manifest.json](../../variants/nu54dk/peripheral-manifest.json) | [M23](verify_m23_inventory.py): PeripheralInventory.inc·09번 matrix | [schema](peripheral-manifest.schema.json), 75개 identity·SDK DTS·singleton·source 계약 |
| [serial-fabric-contract.json](../../variants/nu54dk/serial-fabric-contract.json) | [M24](verify_m24_serial_contract.py): 10번 route/API 계약 | [schema](serial-fabric-contract.schema.json), 5개 block·23개 identity·GPIO/IRQ·public API |
| [system-capability-contract.json](../../variants/nu54dk/system-capability-contract.json) | [M26](verify_m26_system_contract.py): 11번 지원 경계 | validator의 16개 disposition과 inventory 대조 |
| [v04_test_plan.json](../../tests/hil/nu54dk/v04_test_plan.json) | [시험 계획](verify_v04_test_plan.py): 12번 시험 목록 | 75개 identity·19개 family·fixture/oracle·실행 범위 |

원본을 변경한 경우 해당 생성기의 기존 `--write`를 실행한다. 변경하지 않은 생성물을
일괄 재기록하거나 역사적 raw evidence를 재생성하지 않는다.
[verify_generated.py](verify_generated.py)는 원본 파일을 쓰지 않고 hash seed 17/101의
독립 Python process 두 번으로 생성한 5개 결과를 비교한다. 이어 저장된 생성물과 UTF-8/LF
계약을 대조한다. Windows Git checkout의 CRLF 변환은 기존 검사와 같이 정규화한다.
이 검사는 M12 `inventory` gate에 포함되며 기존 각 validator도 계속 별도로 실행한다.

```powershell
python tools/peripheral/verify_generated.py
python tools/peripheral/verify_m23_inventory.py --ncs-root C:\ncs\v3.4.0
python tools/peripheral/verify_m24_serial_contract.py --ncs-root C:\ncs\v3.4.0
```

Profile/feature schema는 builder configuration 모듈과 library의 기존 `nucode.features.yml`,
`variants/nu54dk/profiles`가 소유한다. Readiness는
[v0.4.0-release-readiness.json](../../variants/nu54dk/v0.4.0-release-readiness.json)이 소유하며
[M27](../release/m27_release.py)의 16개 gate 검사가 이를 대조한다. 생성기 성공으로
readiness/HIL/public 지원 수준을 올리지 않는다.

`EXPECTED_*`의 하드웨어·공개 API 상수는 원본 오류를 잡는 독립 검증 oracle이므로
검사 대상 JSON에서 다시 만들어 비교하지 않는다. 생성물의 실제 원본만 한 곳으로 유지한다.
R13의 변경·증거는 [64번 기록](<../../00_Docs/04_검증 기록/64_R13_도구_정책_build_구조.md>)에 연결한다.
