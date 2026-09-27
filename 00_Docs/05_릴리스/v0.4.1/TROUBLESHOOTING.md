# v0.4.1 Troubleshooting

> **보존 문서·지원 종료:** 현재 정식 설치·지원 버전은 [v0.5.0](../v0.5.0/README.md) 하나입니다.
> 아래 지원 범위·설치 명령·검증 결과·예정 작업은 `v0.4.1` 작성 당시의 기록이며 현행 설치 안내가 아닙니다.
> 이 버전은 지원·stable catalog 공급 대상이 아니며, 당시 판정·source·자산 식별값은 보존합니다.

## Boards Manager에 0.4.1이 보이지 않음

Additional Boards Manager URLs가 다음 stable index인지 확인하고 index를 새로 고칩니다.

```text
https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json
```

v0.4.1 공개 당시 stable index는 `0.4.1` 하나만 제공했고 별도 preview/RC index를 사용하지 않았습니다.
현재 index는 `0.5.0`만 제공하므로 v0.4.1이 보이지 않는 것은 지원·catalog 공급 종료에 따른 정상 상태입니다.
신규 설치·문제 해결은 [v0.5.0 안내](../v0.5.0/README.md)를 따릅니다.

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
