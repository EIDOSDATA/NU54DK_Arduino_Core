# 이전 버전에서 v0.4.1로 이동

v0.4.1 이전 버전은 지원하지 않습니다. Arduino Boards Manager에서 `0.4.1`을 설치하고 Sketch를
다시 빌드하십시오. 기존 설치를 유지한 채 문제를 재현하거나 구버전으로 downgrade하는 흐름은
지원 절차가 아닙니다.

## Sketch 호환성

v0.4.0에서 사용하던 `standard`, `ble`, `fabric` profile과 공개 API는 그대로입니다. 일반
Sketch는 소스 수정이 필요하지 않습니다. 직접 peripheral instance를 사용하는 Sketch는 기존과
같이 `Peripheral Fabric (DAP UART disconnected)`을 선택해야 합니다.

## 설치 확인

1. stable index URL을 새로 고칩니다.
2. Boards Manager에 `0.4.1`만 표시되는지 확인합니다.
3. `nucode:zephyr@0.4.1`을 설치합니다.
4. prerequisite 최종 PASS와 실제 빌드 결과를 확인합니다.

과거 tag·Release는 감사용 보존 자료이며 지원 package 선택지가 아닙니다.
