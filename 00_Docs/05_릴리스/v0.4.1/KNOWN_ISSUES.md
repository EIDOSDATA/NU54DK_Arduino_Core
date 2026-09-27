# v0.4.1 Known Issues

> **보존 문서·지원 종료:** 현재 정식 설치·지원 버전은 [v0.5.0](../v0.5.0/README.md) 하나입니다.
> 아래 지원 범위·설치 명령·검증 결과·예정 작업은 `v0.4.1` 작성 당시의 기록이며 현행 설치 안내가 아닙니다.
> 이 버전은 지원·stable catalog 공급 대상이 아니며, 당시 판정·source·자산 식별값은 보존합니다.

## 지원 제한

- **이전 버전:** v0.4.1 이전 stable·RC·preview는 지원하지 않으며 stable Boards Manager
  목록에서 제공하지 않습니다. 과거 공개 자산은 감사 목적으로만 보존합니다.
- **QDEC20/21:** 기본 정·역회전과 SAMPLE/REPORT event 누산은 지원합니다. 동작 중 반복
  manual `read()/clear`의 무손실 누산은 보증하지 않습니다.
- **Serial handover:** 반복 personality 전환은 검증·보증 범위에서 제외합니다.
- **동시성:** 모든 주변장치 동시 조합을 보증하지 않습니다. 같은 block·pin·event·DMA 충돌은
  fail-closed로 거부됩니다.
- **계측 품질:** 정밀 ADC 정확도, jitter, 음질과 신호 무결성은 기능시험 범위 밖입니다.
- **제품선 밖:** Native USB, Loader/LLEXT, OTA/DFU, Wi-Fi와 Ethernet은 지원 범위가 아닙니다.

## 보드 조건

- `fabric` profile에서 DAP UART 공유 pin을 쓰려면 해당 UART switch를 분리해야 합니다.
- active debugger는 watchdog, System OFF와 reset cause 관측에 영향을 줄 수 있습니다.
- P2.7~P2.10 dedicated21 bank는 stock NU54DK의 공개 route가 아닙니다.
