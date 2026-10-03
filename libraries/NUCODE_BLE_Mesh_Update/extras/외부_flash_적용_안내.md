# Mesh update 외부 flash 적용 안내

NU54DK 기본 보드 정의에는 검증된 외부 flash 부품이 없으므로 기본 Mesh update 경로는 내부
`slot1_partition`을 사용한다. 내부 저장소 경로는 BLOB 10/10회와 signed Mesh DFU 5회·두 target
10/10 배포, confirm/rollback·negative·STOP 검증을 완료했다. 결과와 적용 범위는
[M32 TODO](<../../../00_Docs/TODO_M32.md>)를 따른다. 이 기능은 미공개 v0.6.0 개발 범위이며
현재 stable v0.5.0에 포함되지 않는다.

동봉한 overlay는 외부 flash용 시작 template다. 부품과 배선을 지정하기 전에는 그대로 빌드하거나
flash하지 않는다. 외부 저장소의 실물 운용은 사용자 후속 `NOT_RUN`이며 내부 저장소의 PASS와 구분한다.

적용 순서는 다음과 같다.

1. 회로의 SPI instance·chip select와 부품의 JEDEC ID·용량·erase/write 특성을 설정한다.
2. Secondary slot partition을 만들고 같은 정의를 application과 MCUboot의 sysbuild domain에 적용한다.
3. MCUboot external flash driver·image alignment·swap mode·sector 수를 실제 부품과 대조한다.
4. 부품 식별 → sector erase/write/readback → signed image upload → test boot → confirm →
   unconfirmed rollback → 전원 재인가를 검증한다.

보드별 실제 결과를 확보하기 전에는 외부 flash 경로를 `NOT_RUN`으로 유지한다. 새 실제 전원 차단
복구 확장은 [M32-W08의 M36 인계](<../../../00_Docs/TODO_M32.md#m32-w08--blob와-mesh-dfu>) 범위를 따른다.
