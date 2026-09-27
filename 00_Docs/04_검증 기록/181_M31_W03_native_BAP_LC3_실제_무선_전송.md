# M31-W03 native BAP unicast LC3 실제 무선 전송

고정 NCS v3.4.0의 upstream `bap_unicast_client`와 `bap_unicast_server`를
NU54DK target으로 빌드하고, 두 보드의 실제 무선 ISO 경로를 확인했다.
clean Core `b28631df3cdc4bcf1c4926730e81eea377f7ef47`, 고정 board
`fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`를 사용했다.

`CONFIG_LIBLC3=y`만 추가하면 고정 SDK에서 FPU 의존성 때문에 `n`으로
해결된다. 저장소의 [설정](../../tests/hil/nu54dk/fixtures/BapNativeLc3/extra.conf)에
`CONFIG_FPU=y`와 `CONFIG_LIBLC3=y`를 함께 고정했고, 양쪽 최종 `.config`에서
두 설정이 `y`임을 확인했다. SDK와 board submodule은 변경하지 않았다.

| 역할 | FLASH | RAM | HEX SHA-256 |
| --- | ---: | ---: | --- |
| client | 361,904 B | 72,592 B | `8b0e801b1b13e3ec2f62e328f83227ae1144220fb50b839cc48ed945037d3a50` |
| server | 355,456 B | 76,353 B | `4ee802007d69a75a5a6ffef96e32eb0050d2feafd25a387c7a49f5d7e08079a3` |

CMSIS-DAP V2 probe identity hash로 두 보드의 역할을 고정하고 AP register를
확인한 뒤 sector flash와 hardware reset을 사용했다. 20.734초 관찰에서
client가 PACS capability와 양쪽 ASE를 검색하고 codec/QoS 설정, enable,
stream start까지 진행했다. LC3 합성 PCM encoder가 client의 두 stream과
server의 한 stream에서 초기화됐다. 40-byte ISO SDU는 client TX 두 stream
각 1,000개, server TX 한 stream 1,000개가 기록됐다. client RX와 server RX는
각각 유효 SDU 1,000개에 도달했다. server는 client의 LC3 frame을 실제로
decode했고 `Decoder failed`는 0회였다. server 수신에서 무효 ISO packet
24개와 이에 따른 PLC 24회를 별도로 기록했다. 이 값은 유효 SDU 분모에
넣지 않았고, 무손실 전송을 주장하지 않는다. upstream client의 RX callback은
수신 개수만 기록하므로 역방향 LC3 decode PASS로 해석하지 않는다.

[exact HIL JSON](evidence/m31-w03-bap-lc3-b28631df/bap-lc3-exact.json)과
[manifest](evidence/m31-w03-bap-lc3-b28631df/bap-lc3-manifest.json)에
익명 probe hash, register, image/config hash, 원본 UART line, 압축한
빌드 로그·HEX의 SHA-256을 보존했다. 개발 후보 시험은 `source_clean=false`로
분리했고 이 판정에 사용하지 않았다.

이는 `W03-01`의 native 한 방향 합성 PCM → LC3 encode → ISO → LC3 decode와
`W03-02`의 native unicast 제어·양방향 ISO 적용성 증거다. 공개 Arduino
unicast API와 역할별 `.ino`, stop/release 20회, peer-loss/잘못된 codec·QoS
negative, 외장 audio 경로는 아직 남았다. 따라서 두 Audio family case와
M31-W03 전체를 완료로 승격하지 않는다.
