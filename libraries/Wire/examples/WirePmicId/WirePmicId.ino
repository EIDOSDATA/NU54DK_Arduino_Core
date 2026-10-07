/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * 온보드 BQ25186의 Device ID를 repeated-start로 읽습니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Standard peripherals (`standard`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) WirePmicId 실행 보드
 * @par Serial Monitor
 * 사용하지 않음
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par 준비물
 * - NU54DK 보드 1대 — 1) WirePmicId 실행 보드
 * @par 설정
 * - Tools → Feature set에서 `standard` profile을 선택합니다.
 * - 이 예제는 Serial Monitor 출력을 필수 결과로 사용하지 않습니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `NUCODE_M7_I2C_RESULT:6A:0C:`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `:RS`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `NUCODE_M7_I2C_READY`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `NUCODE_M7_I2C_ERROR:TX` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `NUCODE_M7_I2C_ERROR:RX` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `NUCODE_M7_I2C_ERROR:PMIC_ID` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `EEPROM/EEPROMPersistence`
 * - `LittleFS/LittleFSPersistence`
 * @par 종료와 재시작
 * - 예제의 stop/end/disconnect 또는 유한 완료 흐름 뒤 오류와 자원 반환을 확인합니다.
 * - 실패 문구와 driver 상태를 확인한 뒤 명시적 reset 또는 예제의 재시작 흐름을 사용합니다.
 * @par 보안
 * - no_security_property_claimed
 * - 이 예제는 별도의 보안 속성을 주장하지 않습니다.
 * @par 제한
 * - Compile·Host 검사는 실제 보드 runtime 또는 외부 제품 상호운용 PASS를 대신하지 않습니다.
 * - 목적과 metadata 조건 밖의 성능·동시성·정밀도는 이 예제의 보증 범위가 아닙니다.
 * @par Negative
 * - wrong_profile_or_missing_sidecar
 * - missing_or_wrong_role_peer
 * - startup_or_runtime_error_reported
 * @par Traceability
 * Recipe `i2c_wire`; 내부 증거 ID는 metadata에서 관리합니다.
 * 직접 upstream 복사 아님; NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`
 * build `clean_installed_compile_required`, runtime `procedure_documented_not_physical_pass`
 * @par Metadata
 * identity `Wire/WirePmicId`, sha256 `26a800ef0d96cf5f2b3410e55e1826f0d0d3e156cf55264be6086fb71a91f3b0`
 * @nucode_example_setup_end */

/**
 * @file WirePmicId.ino
 * @brief 온보드 BQ25186의 Device ID를 repeated-start로 읽습니다.
 * @note Wire library와 함께 배포되는 NU54DK 전용 PMIC 예제입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Wire.h>

#include <string.h>

namespace
{
    /** @brief NU54DK 온보드 BQ25186의 고정 7-bit 주소입니다. */
    constexpr uint8_t pmic_address = 0x6AU;

    /** @brief BQ25186 MASK_ID register입니다. */
    constexpr uint8_t mask_id_register = 0x0CU;

    /** @brief MASK_ID 하위 nibble에 있는 Device ID mask입니다. */
    constexpr uint8_t device_id_mask = 0x0FU;

    /** @brief BQ25186이 반환해야 하는 Device ID입니다. */
    constexpr uint8_t device_id_expected = 0x01U;

    /** @brief HIL host가 보낼 수 있는 유일한 고정 요청입니다. */
    constexpr char request_token[] = "NUCODE_M7_I2C_PMIC_ID_RS:6A:0C";

    /** @brief UART protocol에서 byte를 두 자리 대문자 16진수로 출력할 표입니다. */
    constexpr char hexadecimal_digits[] = "0123456789ABCDEF";

    char request_buffer[sizeof(request_token)] = {};
    size_t request_length = 0U;
    bool request_overflow = false;

    /**
	 * @brief BQ25186 MASK_ID를 no-STOP pointer write와 repeated-start read로 읽습니다.
	 *
	 * 첫 I2C transaction은 PMIC의 기본 160초 watchdog을 시작합니다. 이 함수는
	 * register 값을 쓰지 않으며 Device ID가 있는 하위 nibble만 판정합니다.
	 */
    void readPmicId(void)
    {
        Wire.beginTransmission(pmic_address);
        if ((Wire.write(mask_id_register) != 1U) || (Wire.endTransmission(false) != 0U))
        {
            Serial.println("NUCODE_M7_I2C_ERROR:TX");
            return;
        }

        if ((Wire.requestFrom(pmic_address, 1U, true) != 1U) || (Wire.available() != 1))
        {
            Serial.println("NUCODE_M7_I2C_ERROR:RX");
            return;
        }

        const int value = Wire.read();
        if ((value < 0) || ((static_cast<uint8_t>(value) & device_id_mask) != device_id_expected))
        {
            Serial.println("NUCODE_M7_I2C_ERROR:PMIC_ID");
            return;
        }

        const uint8_t register_value = static_cast<uint8_t>(value);
        Serial.print("NUCODE_M7_I2C_RESULT:6A:0C:");
        Serial.print(hexadecimal_digits[(register_value >> 4U) & 0x0FU]);
        Serial.print(hexadecimal_digits[register_value & 0x0FU]);
        Serial.println(":RS");
    }

    /** @brief 완성된 UART 줄이 고정 HIL 요청과 같은 경우에만 I2C를 실행합니다. */
    void finishRequest(void)
    {
        request_buffer[request_length] = '\0';
        if (!request_overflow && (request_length == (sizeof(request_token) - 1U)) &&
            (strcmp(request_buffer, request_token) == 0))
        {
            readPmicId();
        }

        request_length = 0U;
        request_overflow = false;
    }

    /**
	 * @brief 한 UART byte를 고정 요청 parser에 반영합니다.
	 *
	 * @param value 수신한 byte입니다.
	 */
    void consumeRequestByte(char value)
    {
        if (value == '\r')
        {
            return;
        }
        if (value == '\n')
        {
            finishRequest();
            return;
        }

        if (request_length < (sizeof(request_buffer) - 1U))
        {
            request_buffer[request_length++] = value;
        }
        else
        {
            request_overflow = true;
        }
    }
} // namespace

/** @brief Serial과 보수적인 100 kHz Wire controller를 시작하고 준비 token을 출력합니다. */
void setup(void)
{
    Serial.begin(115200U);
    Wire.begin();
    Wire.setClock(100000U);
    Serial.println("NUCODE_M7_I2C_READY");
}

/** @brief 고정 UART 요청만 수신하며 I2C 주소 탐색은 수행하지 않습니다. */
void loop(void)
{
    while (Serial.available() > 0)
    {
        const int value = Serial.read();
        if (value < 0)
        {
            break;
        }
        consumeRequestByte(static_cast<char>(value));
    }
    delay(1U);
}
