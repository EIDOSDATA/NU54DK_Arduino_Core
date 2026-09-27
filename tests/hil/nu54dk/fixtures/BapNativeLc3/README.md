# NU54DK native BAP unicast LC3 적용성 시험 설정

고정 NCS v3.4.0의 `zephyr/samples/bluetooth/bap_unicast_client` 및
`bap_unicast_server`를 각각 `nrf54l15dk/nrf54l15/cpuapp/nu54dk` 대상으로
빌드할 때 `-DEXTRA_CONF_FILE=<이 디렉터리의 extra.conf>`를 전달한다.
`CONFIG_FPU=y`는 고정 SDK의 `CONFIG_LIBLC3=y` 의존성을 만족시킨다.

이 설정은 upstream native 샘플의 실제 LC3 encode/서버 decode와 ISO 전송
적용성을 조사한다. Arduino 공개 API나 설치 예제를 대신하지 않는다. 이 fixture가 담당한
native 적용성은 W03 완료 근거의 일부이며, fixture build 하나를 W03 전체 PASS로 계산하지 않는다.
