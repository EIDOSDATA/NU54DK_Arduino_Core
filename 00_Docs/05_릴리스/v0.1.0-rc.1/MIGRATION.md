# v0.1.0-rc.1 마이그레이션 기록

> 보존 문서: `v0.1.0-rc.1`은 [최초 배포 철회 기록](WITHDRAWAL.md)에 따라 이미 회수된 RC입니다. 아래는 당시 계약·기록이며,
> 현재 설치·지원은 [v0.3.0 안내](../v0.3.0/README.md)를 따릅니다. [원본 보존](<../../04_검증 기록/106_Git_이력_정리와_구버전_패키지_공급_종료.md>)

## 당시 전환과 변경점

- 전환: M10 preview·소스 빌드 → 첫 RC.
- Loader/LLEXT 없이 Sketch와 Zephyr를 하나의 ELF/HEX로 빌드하는 첫 배포 후보였다.
- Windows `post_install` 출력의 invalid UTF-8 gRPC 오류 때문에 회수됐다. 관측된 오류는 설치가 끝나도 IDE가 실패로 표시하는 문제였다. 신규 설치·downgrade 대상으로 사용하지 않는다.

## 재현할 때 유지할 경계

- 보드 FQBN은 `nucode:zephyr:nu54dk`, 기준 NCS는 v3.4.0, Toolchain은 `dcbdc366a1`이다.
- 과거 설치 명령·per-tag URL은 현재 제공되는 설치 경로가 아니다. 원본 artifact와 source identity를 먼저 대조한다.
- 버전 전환 전 Sketch·저장 데이터를 백업한다. 공유 NCS/Toolchain을 임의 삭제하거나 다른 version의 build output을 섞지 않는다.
- Storage API가 있는 버전은 EEPROM의 명시적 `commit()`과 LittleFS의 비파괴 mount를 따른다. Format/reset은 데이터 삭제이며 자동 진단 수단이 아니다.

## 근거와 현재 이동 경로

[배포 중단 기록](WITHDRAWAL.md)에 당시 source·검증 결과가 있다. 상세한 예전 설치 순서는
[정리 전 문서 원본](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/blob/0dda7f9dac30845e4fdb8f9bd28da22a906dcb9d/00_Docs/05_%EB%A6%B4%EB%A6%AC%EC%8A%A4/v0.1.0-rc.1/MIGRATION.md)으로 보존한다.
현재 사용자는 [v0.3.0 마이그레이션](../v0.3.0/MIGRATION.md)을 따른다.
