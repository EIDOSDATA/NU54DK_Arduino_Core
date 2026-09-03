# v0.1.0-rc.1 배포 중단 기록

| 항목 | 내용 |
| --- | --- |
| 판정일 | 2026-08-28 |
| 판정 | **배포 중단·회수** |
| 영향 버전 | `0.1.0-rc.1` |
| 교정 버전 | `0.1.0-rc.2` |
| 작성자 | Quantum / NUCODE |

## 1. 배포 중단 이유

Arduino IDE 2.3.10에서 `0.1.0-rc.1`을 Boards Manager로 최초 설치하면 Nordic prerequisite를
설치하는 `post_install` 출력에 UTF-8이 아닌 바이트가 포함될 수 있다. Arduino IDE backend가
그 출력을 gRPC 문자열로 전달하는 과정에서 다음 오류를 표시한다.

```text
Error: 13 INTERNAL: grpc: error while marshalling: string field contains invalid UTF-8
```

화면에는 `Failed to install platform`이 표시되지만, 관찰된 재현에서는 platform 설치와
NCS/Toolchain prerequisite 구성이 이미 끝나 있었다. Arduino IDE log에도 platform
`installed`와 `loaded`가 기록됐고, 설치 디렉터리와 prerequisite `ready.json`이 존재했으며
IDE에 포함된 Arduino CLI가 `nucode:zephyr:nu54dk`를 열거했다.

따라서 이 결함은 firmware, DTS, pyOCD 또는 CMSIS-DAP의 결함이 아니라 **설치 완료 결과를
IDE에 반환하는 출력 인코딩 경로의 결함**이다. 다만 사용자가 성공과 실패를 신뢰성 있게
구분할 수 없으므로 설치가 끝날 수 있다는 사실만으로 배포를 계속하지 않는다.

## 2. 기존 검증 기록의 취급

`v0.1.0-rc.1`에서 수행한 M11 필수 gate 8/8, archive checksum, Arduino CLI package compile,
pyOCD Upload와 UART READY 기록은 실제 수행된 역사적 증거로 유지한다. 이 기록을 삭제하거나
`v0.1.0-rc.2`의 증거로 이름만 바꾸지 않는다.

해당 gate는 Arduino IDE GUI의 긴 `post_install` 실행과 gRPC 완료 응답을 끝까지 검증하지
않았다. 공개 index 검색 성공도 실제 Boards Manager 설치 완료 callback 검증을 대신하지
않는다. 그러므로 `v0.1.0-rc.1`의 기술 gate 통과 기록과 배포 적합성 회수 판정은 서로
모순되지 않는다.

## 3. 사용자 조치

- `v0.1.0-rc.1`을 새로 설치하지 않는다.
- 이미 설치했고 `NUCODE NU54DK Zephyr Boards`가 installed로 표시된다면 NCS/Toolchain을
  수동 삭제하지 않는다. `v0.1.0-rc.2`가 공개된 뒤 Boards Manager에서 업그레이드한다.
- 화면 오류 뒤 실제 설치 여부는 IDE를 재시작하고
  `NU54DK (nRF54L15, Zephyr)` 보드가 선택 가능한지 확인한다.
- `v0.1.0-rc.1` 전용 index URL을 Additional Boards Manager URLs에서 `rc.2` URL로 바꾼다.

## 4. 교정과 재발 방지

`v0.1.0-rc.2`는 다음 변경을 포함하는 별도 immutable artifact로 만든다.

- `post_install.bat`이 PowerShell 실행 전에 Windows console code page를 UTF-8로 고정
- prerequisite PowerShell runner의 console input/output과 native command 출력 인코딩을
  BOM 없는 UTF-8로 고정
- 설치 출력이 UTF-8로 decode 가능한지 확인하는 host 회귀 추가
- Arduino IDE bundled backend의 실제 설치·완료 응답 경로 재검증

`v0.1.0-rc.2`는 새 source commit, archive, index, checksum과 evidence를 가져야 한다.
`v0.1.0-rc.1` artifact나 tag를 덮어써서 교정하지 않는다.

## 5. 원격 공개 상태

프로젝트 소유자는 `v0.1.0-rc.1` 폐기와 교정 RC 배포를 승인했다. GitHub Prerelease, tag와
RC index는 2026-08-28T12:16:20Z까지 삭제했고 원격 tag도 제거했다. 공개 Release 자산은
더 이상 다운로드할 수 없다. 당시의 commit과 M11 8/8 검증 결과는 재현성과 감사 목적의
역사적 문서로만 유지한다.

교정 버전 `v0.1.0-rc.2`는 2026-08-28T12:14:28Z에 별도 GitHub Prerelease로 공개했으며,
공개 index와 ZIP을 다시 내려받은 Arduino IDE 2.3.10 backend gRPC 설치가 정상 완료됐다.
