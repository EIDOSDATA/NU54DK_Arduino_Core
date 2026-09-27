# v0.3.0-rc.2 마이그레이션 기록

> **보존 문서·지원 종료:** 현재 정식 설치·지원 버전은 [v0.5.0](../v0.5.0/README.md) 하나입니다.
> 아래 지원 범위·설치 명령·검증 결과·예정 작업은 `v0.3.0-rc.2` 작성 당시의 기록이며 현행 설치 안내가 아닙니다.
> 이 버전은 지원·stable catalog 공급 대상이 아니며, 당시 판정·source·자산 식별값은 보존합니다.
> 2026-09-08 공개 공급 종료와 원본 보관 경로는 [106번 기록](<../../04_검증 기록/106_Git_이력_정리와_구버전_패키지_공급_종료.md>)을 따릅니다.

## 당시 전환과 변경점

- 전환: v0.2.0 stable·RC1 → RC2.
- Nordic installer가 설치 leaf를 직접 생성하도록 clean-room 실행기를 교정했다. RC1 기능·예제 범위를 새 identity에서 다시 검증했다.
- 공개 설치·29개 예제 compile·Upload·clean-room 수명주기는 통과했다. RRAM 표시/linker 경계 문제는 후속 RC3의 별도 교정이며 RC2 PASS를 전체 memory 계약 보증으로 확대하지 않는다.

## 재현할 때 유지할 경계

- 보드 FQBN은 `nucode:zephyr:nu54dk`, 기준 NCS는 v3.4.0, Toolchain은 `dcbdc366a1`이다.
- 과거 설치 명령·per-tag URL은 현재 제공되는 설치 경로가 아니다. 원본 artifact와 source identity를 먼저 대조한다.
- 버전 전환 전 Sketch·저장 데이터를 백업한다. 공유 NCS/Toolchain을 임의 삭제하거나 다른 version의 build output을 섞지 않는다.
- Storage API가 있는 버전은 EEPROM의 명시적 `commit()`과 LittleFS의 비파괴 mount를 따른다. Format/reset은 데이터 삭제이며 자동 진단 수단이 아니다.

## 근거와 현재 이동 경로

[RC2 검증 기록](<../../04_검증 기록/30_M22_v0.3.0_rc2_통합_릴리스_기준선.md>)에 당시 source·검증 결과가 있다. 상세한 예전 설치 순서는
[정리 전 문서 원본](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/blob/0dda7f9dac30845e4fdb8f9bd28da22a906dcb9d/00_Docs/05_%EB%A6%B4%EB%A6%AC%EC%8A%A4/v0.3.0-rc.2/MIGRATION.md)으로 보존한다.
현재 사용자는 [v0.5.0 마이그레이션](../v0.5.0/MIGRATION.md)을 따른다.
