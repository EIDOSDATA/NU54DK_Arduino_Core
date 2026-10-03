/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) FlushableAclData 적용성 확인 보드
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 고정 Zephyr Host에는 flushable LE ACL TX path가 없어 전송 예제가 아니라 적용성 경계 보고 예제입니다.
 * @par Metadata
 * identity `NUCODE_BLE/FlushableAclData`, sha256 `8699a4f8c61a2019b2b80c9db40c273641fc545ce1377fb1f8f84e08f907bdf4`
 * @nucode_example_setup_end */

/**
 * @file FlushableAclData.ino
 * @brief experimental LE Flushable ACL controller와 고정 Host TX 적용 경계를 출력합니다.
 */

#include <NUCODE_BLE.h>

void setup()
{
    Serial.begin(115200);
    if (!BLEDevice.begin("NU54-FLUSH-ACL"))
    {
        Serial.println("BLE start failed");
        return;
    }
    const nucode::ble::BLEFlushableAclSupport support =
        BLENordic.flushableAclSupport();
    Serial.print("Controller experimental: ");
    Serial.println(support.controller_experimental ? "yes" : "no");
    Serial.print("Zephyr Host flushable TX path: ");
    Serial.println(support.host_transmit_path ? "yes" : "no");
    Serial.println(support.usable
                       ? "Flushable ACL usable"
                       : "NOT SUPPORTED: Host LE ACL TX uses non-flushable boundary");
}

void loop()
{
    BLEDevice.poll();
}
