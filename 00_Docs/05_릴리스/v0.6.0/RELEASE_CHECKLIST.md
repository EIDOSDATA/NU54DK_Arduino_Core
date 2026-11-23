# v0.6.0 배포 체크리스트

2026-11-24 KST에 **v0.6.0을 공개**했습니다. 다섯 Host 검증과 최종 패키지 심사, 자산 게시 및 공개 설치의 증거를 아래에 연결합니다.

| 단계 | 판정 |
| --- | --- |
| 다섯 목표 환경의 배정 실기와 후속 검증 | 완료. [지원표](SUPPORT_MATRIX.md) |
| 최종 후보와 자산 재현성 | 완료. Core 이미지 소스 `0a63c501ccd0d2e26298f1ad98a81a99cddc565f`. [339번 검증 기록](<../../04_검증 기록/339_HOST_W08_v0.6.0_최종_후보와_배포_자산_준비.md>) |
| 공개 승인 | 완료. 승인된 계획의 SHA-256 `fd256802e5a132e01265be62d9b9d4b3959059ba19b4e9c99b87d44c50555f81`. |
| GitHub Release와 자산 | 초기 Python 3개와 Core 자산 6개 공개 및 다운로드 해시 대조 완료. [릴리스](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/tag/v0.6.0) |
| stable 인덱스 | `21819ea1df010625ec366fd367de279e5a42b3a1` 게시와 공개 URL 해시 확인 완료. [인덱스](https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json) |
| 공개 설치 | macOS 27.2.1 신규 설치, 예제 발견, 대표 빌드와 제거 후 재설치 통과. [340번 기록](<../../04_검증 기록/340_v0.6.0_정식_게시와_공개_설치_검증.md>) |

W06은 실제 PASS 46건과 사용자 수락 3건으로 기록합니다. #29의 원인 분석은 유예 상태입니다. SDK 전환은 [v0.7.0 계획](../../TODO_v0.7.0.md)에 있습니다.
