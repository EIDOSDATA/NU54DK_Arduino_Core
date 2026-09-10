# v0.4.0-rc.1 Known Issues — 비공개 후보

## 지원 제한

- **QDEC20/21:** manual read/clear 중 간헐 누산 누락이 재현됐습니다. 추가 진단은 제외했고
  `NUCODE_Peripheral_Fabric` capability는 `unsupported`입니다.
- **동시성 범위:** 각 공개 identity의 단독 HIL은 통과했지만 manifest의
  `concurrent_hil=partial/not_run`인 조합은 지원 보증이 아닙니다. 동일 block·pin·event·DMA 자원
  충돌은 fail-closed로 거부됩니다.
- **Serial handover:** 반복 personality 전환은 최종 필수 범위에서 제외했습니다. 정상
  begin/end·stop/restart와 동일한 결함으로 해석하지 않습니다.
- **외부 품질:** 정밀 ADC 정확도, clock jitter, 오디오 품질, 신호 무결성과 모든 sensor·codec·
  microphone 호환성은 합의한 기능 HIL 범위 밖입니다.

## 보드 조건

- `fabric` profile 이름의 DAP UART disconnected 조건은 실제 switch 상태를 뜻합니다. DAP UART가
  같은 핀을 계속 구동하면 데이터 오류나 ownership 외부 충돌이 생길 수 있습니다.
- WDT30과 System OFF를 관측할 때 active debugger가 halt/reset/power 동작을 바꿀 수 있습니다.
- P2.7~P2.10의 dedicated21 bank는 LED·SWO·PMIC net 충돌 때문에 stock NU54DK 공개 route가 아닙니다.

## 릴리스 상태

현재 후보는 공개 package가 아닙니다. 과거 staging 29/29 결과는 최종 30개 예제의 Boards Manager
수명주기 검증을 대신하지 않습니다. T20~T21 기술 gate와 T22 소유자 승인 전에는 이 문서를
설치 완료 또는 stable 공개 근거로 사용하지 마십시오.
