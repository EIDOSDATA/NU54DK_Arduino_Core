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
