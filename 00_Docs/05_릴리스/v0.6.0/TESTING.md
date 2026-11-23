# v0.6.0 검증 근거와 재실행 범위

전체 빌드 기준선, OS별 실기, IDE Upload 수정은 서로 다른 소스에서 검증했습니다. 아래 표에서 재현하려는 항목의 소스와 기록을 먼저 선택하세요.

| 증거 단위 | exact source | 범위·색인 |
| --- | --- | --- |
| HOST-W06 H12 | `6364a1d9955f79fef0ac1f3219883a9d77e24f32` | 당시 세 native OS 전체 빌드와 image 비교, [322번](<../../04_검증 기록/322_HOST_W06_H12_native_전체_검증_마감과_W07_준비.md>) |
| C5 최신 전체 기준선 | `5ee7c10368b554ca23d68f8f82e39308b91df6de` | NUS 교정 후 OS별 예제 204개 빌드, 프로필 거부 검사 9개, [328번](<../../04_검증 기록/328_HOST_W07_C5_필수_자동검증과_사용자_OS_gate.md>). Windows 11 후속 실기는 [329번](<../../04_검증 기록/329_M33_W07_v0.6.0_OS_지원_범위와_Windows11_진행.md>) |
| C10 WSL2 | `4890f697ab80dfed3cff62bd42acc42b0f3e1a34` | Ubuntu 24.04 기준선과 26.04 호환성, [330번](<../../04_검증 기록/330_HOST_W07_C6_WSL2_지원과_Ubuntu24.04_검증.md>) |
| C11 Mac software | `d304f369c0d3ebbac35c3bf0ef3b7b2887f40dfa` | [CI43760678488 attempt1](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/43760678488), 5/5 성공, [331번](<../../04_검증 기록/331_HOST_W07_C11_macOS_26_27_호환성.md>) |
| C11 문서 후속 | `4d7dff44666b0ab1c01311bf6350dd675d6f8e9e` | [CI43763189943 attempt1](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/43763189943), 8건 통과, 범위 밖 1건 생략. 문서 커밋에서 실행 |
| C12 IDE Upload 교정 | `97c7cd01ff59fb5ae3689e9de62b9c820b83fd5e` | macOS27 실제 IDE Upload·Blink 동작, C11 standard Blink BIN/HEX 동일. [C12 CI 9개 작업 통과](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/45207890683). [338번](<../../04_검증 기록/338_HOST_W07_macOS_27_Arduino_IDE_Upload_교정.md>) |
| 최종 버전 후보 | `0a63c501ccd0d2e26298f1ad98a81a99cddc565f` | macOS 27 CLI 설치 전이와 설치 파일 960개 대조, 예제 204개 발견. Blink 이미지가 C12와 일치했고 BoardInfo에 새 버전이 들어 있다. [339번 기록](<../../04_검증 기록/339_HOST_W08_v0.6.0_최종_후보와_배포_자산_준비.md>) |

C11의 Mac CI는 각 OS에서 설치 파일 960개와 예제 204개를 확인하고 대표 예제 4개씩 cold/warm 빌드를 수행했습니다. 관련 단위 검사 결과는 OS별 PASS 67건, 조건부 SKIP 3건입니다. 두 Mac의 대표 BIN 및 HEX가 바이트 단위로 일치했습니다. 실제 기기의 USB 재연결과 UART 판정은 [336번 기록](<../../04_검증 기록/336_HOST_W07_C11_macOS_26_실기_검증과_재연결.md>), [337번 기록](<../../04_검증 기록/337_HOST_W07_C11_macOS_27_실기_검증과_마감.md>)에 있습니다.

C12는 Mac의 일반 IDE Upload에서 플래시 20개 섹터(81,920바이트)를 기록했고, GPIO 전이 9회와 사용자의 LED 점멸 관찰을 확인했습니다. 이때 사용한 standard Blink의 BIN과 HEX는 C11과 일치했습니다. [338번 기록](<../../04_검증 기록/338_HOST_W07_macOS_27_Arduino_IDE_Upload_교정.md>)

## 최종 배포 검증

| 계약 case | 지금 연결할 수 있는 근거 | 최종 잔여 |
| --- | --- | --- |
| `M33-PACKAGE-01` | C5 package 재현·설치 발견·전체 기준선, C11 kit/producer 원본과 222개 파일 hash 감사 | 정식 배포 source·version·plan·archive hash와 재현 결과 고정 |
| `M33-INSTALL-01` | Windows11 C5, WSL2 C10, Mac software·실기 C11의 배정 PASS를 [지원표](SUPPORT_MATRIX.md)에 연결 | 최종 package의 설치 전이와 변경 영향 확인 |
| `M33-RELEASE-01` | [공개 전 체크리스트](RELEASE_CHECKLIST.md) 준비 | exact plan 승인·게시·공개 URL 설치 모두 미실행 |

[m33-release-readiness.json](../../../variants/nu54dk/m33-release-readiness.json)은 생성된 strict 기능/원형 case 원장이다.
그 안의 W07 미착수·package/install `NOT_RUN`을 현재 Host 준비가 없다는 뜻으로 읽지 않는다.
현행 진행은 [host-readiness.json](../../../variants/nu54dk/host-readiness.json)이 소유하며, 최종 case 판정은
실제 종료 근거를 갖춘 뒤 생성원본과 함께 갱신한다. 이번 문서 작업은 strict 원장을 소급 승격하지 않는다.

## 필요한 때에만 확대

OS 버전이나 문서 SHA만 달라졌다는 이유로 전체 빌드를 반복하지 않는다.
SDK/compiler·firmware·compile 설정이 바뀌거나 실패 분석에서 영향이 확인되면 해당 범위만 재검증한다.
전체 영향이 확인된 경우에만 전체 시험을 배정한다. 기존 FAIL과 중단 기록은 새 PASS로 덮어쓰지 않는다.
