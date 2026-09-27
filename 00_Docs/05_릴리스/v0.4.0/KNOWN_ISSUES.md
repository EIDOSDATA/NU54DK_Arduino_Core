# v0.4.0 Known Issues

> **보존 문서·지원 종료:** 현재 정식 설치·지원 버전은 [v0.5.0](../v0.5.0/README.md) 하나입니다.
> 아래 지원 범위·설치 명령·검증 결과·예정 작업은 `v0.4.0` 작성 당시의 기록이며 현행 설치 안내가 아닙니다.
> 이 버전은 지원·stable catalog 공급 대상이 아니며, 당시 판정·source·자산 식별값은 보존합니다.

## 지원 제한

- **QDEC20/21:** 기본 정·역회전과 SAMPLE/REPORT event 누산은 지원합니다. 동작 중 반복
  manual `read()/clear`에서는 간헐 누산 누락이 재현됐으므로 이 사용 방식의 무손실 누산은
  보증하지 않습니다.
- **동시성 범위:** 공개 identity의 단독 HIL은 통과했지만 manifest의
  `concurrent_hil=partial/not_run` 조합은 지원 보증이 아닙니다. 동일 block·pin·event·DMA
  충돌은 fail-closed로 거부됩니다.
- **Serial handover:** 반복 personality 전환은 최종 필수 범위에서 제외했습니다. 정상
  begin/end·stop/restart와 같은 결함으로 해석하지 않습니다.
- **외부 품질:** 정밀 ADC 정확도, clock jitter, 오디오 품질, 신호 무결성과 모든 sensor·codec·
  microphone 호환성은 기능 HIL 범위 밖입니다.
- **제품선 밖:** Native USB, Loader/LLEXT, OTA/DFU, Wi-Fi와 Ethernet은 v0.4.0 범위가
  아닙니다.

## 보드 조건

- `fabric` profile의 DAP UART disconnected 조건은 실제 switch 상태를 뜻합니다. 공유 pin을
  DAP UART가 계속 구동하면 외부 충돌이나 데이터 오류가 발생할 수 있습니다.
- WDT30과 System OFF 관측은 active debugger의 halt/reset/power 영향과 구분해야 합니다.
- P2.7~P2.10 dedicated21 bank는 LED·SWO·PMIC net 충돌 때문에 stock NU54DK 공개 route가
  아닙니다.

## 배포 상태

`v0.4.0`은 GitHub Release와 stable index에 정식 공개됐습니다. Package는 2,630,374 byte,
SHA-256 `6629963fc618419135b4fc0c1240fa84fa1db95fad03b92add798bbacf0c9189`이며 공개 URL의
설치·예제 30/30 compile·실제 Upload·전환·제거·재설치까지 PASS했습니다. 상세 identity와 근거는
[125번 기록](<../../04_검증 기록/125_v0.4.0_정식_릴리스_공개와_T24_T25_마감.md>)을 따릅니다.
