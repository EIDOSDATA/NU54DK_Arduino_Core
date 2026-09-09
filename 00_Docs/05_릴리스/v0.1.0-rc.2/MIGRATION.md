# v0.1.0-rc.2 마이그레이션 기록

> 보존 문서: `v0.1.0-rc.2`의 공개 공급은 2026-09-08 종료됐습니다. 아래 내용은 당시 계약·기록이며,
> 현재 설치·지원은 [v0.3.0 안내](../v0.3.0/README.md)를 따릅니다. [원본 보존](<../../04_검증 기록/106_Git_이력_정리와_구버전_패키지_공급_종료.md>)

## 당시 전환과 변경점

- 전환: 회수된 RC1·M10 preview·소스 빌드 → RC2.
- Windows console·PowerShell·native command 출력을 UTF-8로 고정했다. RC1의 firmware·DTS·pin·Upload payload는 변경하지 않았다.
- NCS와 Toolchain의 exact pin·완료 marker가 일치하면 공유 설치를 재사용했다. 공개 후 수동 clean Windows 검증을 자동 gate 8/8로 소급하지 않는다.

## 재현할 때 유지할 경계

- 보드 FQBN은 `nucode:zephyr:nu54dk`, 기준 NCS는 v3.4.0, Toolchain은 `dcbdc366a1`이다.
- 과거 설치 명령·per-tag URL은 현재 제공되는 설치 경로가 아니다. 원본 artifact와 source identity를 먼저 대조한다.
- 버전 전환 전 Sketch·저장 데이터를 백업한다. 공유 NCS/Toolchain을 임의 삭제하거나 다른 version의 build output을 섞지 않는다.
- Storage API가 있는 버전은 EEPROM의 명시적 `commit()`과 LittleFS의 비파괴 mount를 따른다. Format/reset은 데이터 삭제이며 자동 진단 수단이 아니다.

## 근거와 현재 이동 경로

[RC2 검증 기록](<../../04_검증 기록/12_M11_v0.1.0_rc2_공개_후_수동_검증.md>)에 당시 source·검증 결과가 있다. 상세한 예전 설치 순서는
[정리 전 문서 원본](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/blob/0dda7f9dac30845e4fdb8f9bd28da22a906dcb9d/00_Docs/05_%EB%A6%B4%EB%A6%AC%EC%8A%A4/v0.1.0-rc.2/MIGRATION.md)으로 보존한다.
현재 사용자는 [v0.3.0 마이그레이션](../v0.3.0/MIGRATION.md)을 따른다.
