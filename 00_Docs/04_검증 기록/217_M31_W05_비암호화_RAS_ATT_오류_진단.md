# M31-W05 비암호화 RAS ATT 오류 진단

`bdea52ba5466f9b4fd9a66327dd391a91e560a02`의 clean source와 exact
client/reflector HEX로 동일 ACL 20회 비암호화 Ranging Features read를 시작했다.
실기 직전 현재 COM14/COM13 역할과 두 probe SHA-256, controller/SoC register를
다시 확인했고 sector flash와 hardware reset만 사용했다.

[첫 실행 원본](evidence/m31-w04-w05-bdea52ba/cs-insecure-same-acl-01.json)은
0/20 **FAIL**로 보존한다. client는 RAS characteristic을 찾았고 첫 read가 ATT
`0x05`로 거부됐으며, STOP 뒤 양측 disconnect까지 확인됐다. 따라서 이 실행은
flash 직후 무응답이나 ACL 중단이 아니라 시험 fixture가 ATT `0x0f`만 허용한
판정 오류다.

NCS v3.4.0의 RAS reflector는 Ranging Features에
`BT_GATT_PERM_READ_ENCRYPT`를 설정한다. Bluetooth Host는 암호화되지 않았고 사용할
LTK가 없는 연결에서 `Insufficient Authentication (0x05)`를 반환할 수 있으며,
암호화가 부족한 상태의 `Insufficient Encryption (0x0f)`도 보안 거부다. fixture와
runner는 두 원본 오류를 모두 보안 negative로 기록하되, 같은 ACL 안에서 오류 코드가
바뀌면 FAIL하도록 수정한다. 어느 경우도 wrong-key negative 검증으로 확대하지 않는다.

## 수정 후 동일 ACL 재실행

`98f22d5ad6febac4f98cc0877561252a91a310b4`의 clean source에서 fixture와
reflector를 다시 빌드해 같은 현재 mapping으로 재실행했다.
[재실행 원본](evidence/m31-w04-w05-98f22d5a/cs-insecure-same-acl-02.json)은
별도 보존한다.

| 판정 범위 | 결과 | 근거와 경계 |
| --- | --- | --- |
| exact image/source | PASS | clean core revision, 두 HEX SHA-256, controller/SoC register 기록 |
| 비암호화 Ranging Features 거부 | PASS | ATT `0x05` 거부 20/20, read 성공 0건 |
| 같은 ACL 반복 read | PASS | 연결 count 1, discovery 1회, retry 19회, 중간 disconnect 0회 |
| retry pacing | PASS | 각 read timestamp 간격이 모두 50 ms 이상 |
| STOP/cleanup | PASS | local reason 22와 reflector disconnect 확인 |
| wrong-key negative | NOT RUN | 이번 fixture는 SMP를 비활성화해 잘못된 LTK를 주입하지 않음 |
| 정밀 거리 정확도 | NOT RUN | RAS read negative이며 거리 계산·보정 결과가 없음 |

flash/reset 전환 구간의 UART에는 각 boot에서 `count=1`인 연결 event가 2개 보였지만,
측정 구간의 discovery는 1회였고 첫 read 이후 재연결·재탐색은 없었다. 따라서 20회
결과는 하나의 측정 ACL에서 얻었으며, 이 전환 event 자체는 별도 flash 직후 안정성
진단 대상으로 남긴다.
