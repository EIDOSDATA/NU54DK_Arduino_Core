# v0.1.0-rc.2 마이그레이션 안내

| 항목 | 내용 |
| --- | --- |
| 대상 | 회수된 `v0.1.0-rc.1`, M10 preview 또는 소스 직접 빌드에서 `v0.1.0-rc.2`로 이동하는 사용자 |
| 배포 상태 | **GitHub Prerelease 공개 완료 — 공개 자산 checksum과 backend 설치 검증 완료** |
| 작성자 | Quantum / NUCODE |
| 구조 | Loader/LLEXT 없는 Native Full Zephyr image |
| 기준 SDK | nRF Connect SDK v3.4.0 / Zephyr 4.4.0 |

## 1. rc.1에서 반드시 이동해야 하는 이유

`v0.1.0-rc.1`은 Arduino IDE가 `post_install` 완료 출력을 gRPC로 전달할 때 invalid UTF-8
오류를 표시할 수 있어 배포를 중단했다. 관찰된 재현에서는 platform과 prerequisite 설치가
끝났지만 IDE가 실패로 표시했다. 자세한 원인과 증거 경계는
[v0.1.0-rc.1 배포 중단 기록](../v0.1.0-rc.1/WITHDRAWAL.md)에 있다.

`v0.1.0-rc.2`는 Windows console과 PowerShell/native command 출력 인코딩을 UTF-8로
고정한다. rc.1 package를 같은 tag나 ZIP에서 덮어쓰지 않고 별도 version과 checksum으로
배포한다.

## 2. 공개 확인

다음 URL은 공개된 `v0.1.0-rc.2` GitHub Prerelease의 고정 RC index다.

```text
https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/download/v0.1.0-rc.2/package_nucode_nu54dk_rc_index.json
```

공개 전에는 해당 URL을 Arduino IDE에 등록하거나 비공식 ZIP을 수동 설치하지 않는다.
README에 RC 공개 완료와 checksum 재다운로드 검증이 기록된 뒤 사용한다.

## 3. rc.1에서 업그레이드

1. Arduino IDE, Serial Monitor와 실행 중인 pyOCD process를 닫는다.
2. Additional Boards Manager URLs에서 rc.1 전용 URL을 제거하고 rc.2 전용 URL을 등록한다.
3. Boards Manager index를 갱신한다.
4. `NUCODE NU54DK Zephyr Boards`의 `0.1.0-rc.2`를 설치한다.
5. IDE를 재시작하고 `NU54DK (nRF54L15, Zephyr)`를 선택한다.
6. Blink를 clean compile한 뒤 기존 Sketch를 빌드한다.

rc.1 설치 중 Nordic prerequisite가 이미 정상 완료됐다면
`%USERPROFILE%\ncs\v3.4.0`과 `%USERPROFILE%\ncs\toolchains\dcbdc366a1`을 먼저 삭제하지
않는다. rc.2 installer가 exact revision과 완료 marker를 확인해 안전한 경우 재사용한다.

## 4. M10 preview 또는 소스 빌드에서 이동

- `0.0.96`과 `0.0.97`은 clean Windows package lifecycle 검증용 preview이며 일반 배포
  version이 아니다.
- `0.0.94`와 `0.0.95`는 PowerShell 5.1 runner 수정 전 실패 이력이므로 이동 기준으로
  사용하지 않는다.
- Boards Manager archive에는 고정된 NU54DK 보드 파일이 포함되므로 사용자가 Git
  submodule을 별도로 설치할 필요가 없다.
- 기존 Zephyr build directory, Arduino 임시 output 또는 M9 cache entry를 새 platform
  directory로 수동 복사하지 않는다.

## 5. 변경되지 않는 계약

- 보드 FQBN은 `nucode:zephyr:nu54dk`다.
- 물리 핀과 peripheral route의 단일 원본은 고정된
  `board_package/NU54DK_Zephyr_DTS`다.
- 기본 Upload는 온보드 CMSIS-DAP V2와 pyOCD이며 외장 J-Link는 선택 경로다.
- Sketch, Core와 Zephyr는 Loader 없이 하나의 ELF/HEX로 정적 링크된다.
- `Serial`은 target native USB CDC가 아니라 DAP UART 기반 Zephyr console wrapper다.

API 범위와 핀 의미는
[Arduino API 지원 범위](<../../01_아두이노 코어 설계/04_Arduino_API_지원_범위.md>)를 따른다.

## 6. 되돌리기와 제거

Boards Manager에서 Core를 제거해도 공유 NCS/Toolchain은 자동 삭제하지 않는다. 이를 수동
삭제하면 다음 설치에서 대용량 다운로드가 다시 수행된다. 회수된 rc.1로 downgrade하지
않는다. Sketch와 사용자 library는 Core 제거 대상이 아니다.
