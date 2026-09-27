# v0.3.0-rc.3 마이그레이션 기록

> **보존 문서·지원 종료:** 현재 정식 설치·지원 버전은 [v0.5.0](../v0.5.0/README.md) 하나입니다.
> 아래 지원 범위·설치 명령·검증 결과·예정 작업은 `v0.3.0-rc.3` 작성 당시의 기록이며 현행 설치 안내가 아닙니다.
> 이 버전은 지원·stable catalog 공급 대상이 아니며, 당시 판정·source·자산 식별값은 보존합니다.
> 2026-09-08 공개 공급 종료와 원본 보관 경로는 [106번 기록](<../../04_검증 기록/106_Git_이력_정리와_구버전_패키지_공급_종료.md>)을 따릅니다.

## 당시 전환과 변경점

- 전환: v0.2.0 stable·RC2 → RC3.
- 사용하지 않던 boot reservation·두 번째 slot을 제거하고 loaderless application을 `0x000000..0x16c000`, 1,490,944 byte로 일치시켰다. DTS·linker·Arduino maximum을 함께 검사한다.
- LittleFS 시작 `0x16c000`과 Settings/ZMS 시작 `0x174000`은 RC2와 같다. 주소가 같아도 데이터 자동 migration·보존을 보증하지 않는다. RC1/RC2로 돌아갈 때의 maximum 712,704 byte는 원본 artifact의 역사 값이다.

## 재현할 때 유지할 경계

- 보드 FQBN은 `nucode:zephyr:nu54dk`, 기준 NCS는 v3.4.0, Toolchain은 `dcbdc366a1`이다.
- 과거 설치 명령·per-tag URL은 현재 제공되는 설치 경로가 아니다. 원본 artifact와 source identity를 먼저 대조한다.
- 버전 전환 전 Sketch·저장 데이터를 백업한다. 공유 NCS/Toolchain을 임의 삭제하거나 다른 version의 build output을 섞지 않는다.
- Storage API가 있는 버전은 EEPROM의 명시적 `commit()`과 LittleFS의 비파괴 mount를 따른다. Format/reset은 데이터 삭제이며 자동 진단 수단이 아니다.

## 근거와 현재 이동 경로

[RC3 검증·인계 기록](<../../04_검증 기록/31_M22_v0.3.0_rc3_검증과_stable_인계.md>)에 당시 source·검증 결과가 있다. 상세한 예전 설치 순서는
[정리 전 문서 원본](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/blob/0dda7f9dac30845e4fdb8f9bd28da22a906dcb9d/00_Docs/05_%EB%A6%B4%EB%A6%AC%EC%8A%A4/v0.3.0-rc.3/MIGRATION.md)으로 보존한다.
현재 사용자는 [v0.5.0 마이그레이션](../v0.5.0/MIGRATION.md)을 따른다.
