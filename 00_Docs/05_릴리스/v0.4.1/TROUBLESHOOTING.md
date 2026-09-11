# v0.4.1 Troubleshooting

## Boards Manager에 0.4.1이 보이지 않음

Additional Boards Manager URLs가 다음 stable index인지 확인하고 index를 새로 고칩니다.

```text
https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json
```

stable index는 `0.4.1` 하나만 제공합니다. 별도 preview/RC index나 캐시된 과거 index를 사용하지
마십시오.

## 설치는 표시됐지만 prerequisite 결과가 불분명함

Arduino의 platform 등록 문구만으로 성공을 판정하지 않습니다. 로그의 최종
`Nordic prerequisite installation PASS`, `status: ready`, 종료 코드가 모두 성공인지
확인하십시오. v0.4.1은 설치 전 복구 가능한 검사의 과거 오류를 최종 실패 뒤에 다시 출력하지
않습니다.

## SDK 경고

symlink 생성이나 CMake 전역 등록 경고는 `nrf/west.yml` 등 고정 파일과 revision의 최종 검증
결과로 판정합니다. 최종 검증이 실패하면 로그 경로, 누락 파일, NCS root를 함께 기록하십시오.

## Runtime 문제

Profile 충돌, 통신, DMA stop, TEMP/WDT/System OFF와 QDEC 진단은 v0.4.0과 같은 기능 경계를
적용합니다. 무한 재시도하지 말고 반환값과 CMSIS-DAP peripheral·DMA·GPIO·오류 레지스터를
확보하십시오.
