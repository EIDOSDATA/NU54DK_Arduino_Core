/**
 * @file NUCODE_BLE_Security.h
 * @brief NUCODE BLE 공통 lifecycle에 결합되는 보안·표준 profile API입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_BLE_SECURITY_H_
#define NUCODE_BLE_SECURITY_H_

#include <NUCODE_BLE.h>

#include <cstddef>
#include <cstdint>

namespace nucode::ble
{

    /** @brief 연결에 요구할 Bluetooth LE 보안 수준입니다. */
    enum class SecurityLevel : std::uint8_t
    {
        none = 1,
        encrypted = 2,
        authenticated = 3,
        secure_connections = 4,
    };

    /** @brief 로컬 장치가 실제로 제공하는 SMP 사용자 입출력 능력입니다. */
    enum class SecurityIoCapability : std::uint8_t
    {
        /** 화면과 숫자 입력 장치가 없으며 Just Works만 사용할 수 있습니다. */
        no_input_output,
        /** passkey를 표시할 수 있지만 사용자가 숫자를 입력할 수 없습니다. */
        display_only,
        /** 사용자가 passkey를 입력할 수 있지만 값을 표시할 수 없습니다. */
        keyboard_only,
        /** passkey 표시와 일치 여부 확인 버튼을 제공합니다. */
        display_yes_no,
        /** passkey 표시·입력·일치 여부 확인을 모두 제공합니다. */
        keyboard_display,
    };

    /** @brief 현재 연결에서 관찰한 bond 수명주기 상태입니다. */
    enum class BondState : std::uint8_t
    {
        /** 저장 bond 후보나 새 bond가 없는 상태입니다. */
        none,
        /** 이번 boot에서 pairing은 끝났지만 재부팅 복원은 아직 검증하지 않은 상태입니다. */
        persistence_pending,
        /** boot 때 로드된 peer가 연결되었지만 저장 key 검증은 아직 끝나지 않은 상태입니다. */
        restored_candidate,
        /** 새 pairing 없이 L2 이상 보안 복원이 성공한 상태입니다. */
        verified,
        /** bond 제거 요청을 stack이 수락했지만 재부팅 후 영속 삭제는 아직 검증하지 않은 상태입니다. */
        removal_requested,
    };

    /** @brief pairing과 bond 수명주기에서 Sketch에 전달하는 event입니다. */
    enum class SecurityEvent : std::uint8_t
    {
        pairing_requested,
        passkey_display,
        passkey_input_requested,
        passkey_confirmation_requested,
        pairing_cancelled,
        paired,
        bond_persistence_pending,
        bond_restored_candidate,
        bond_verified,
        pairing_failed,
        security_changed,
        bond_removal_requested,
        all_bonds_removal_requested,
        timeout,
        error,
    };

    /** @brief BLE 보안·표준 profile의 공개 오류 분류입니다. */
    enum class SecurityError : std::uint8_t
    {
        none,
        invalid_argument,
        invalid_context,
        not_initialized,
        not_connected,
        invalid_state,
        busy,
        timeout,
        rejected,
        storage_error,
        not_subscribed,
        driver_error,
    };

    /** @brief Zephyr type을 공개하지 않는 Bluetooth LE identity 주소입니다. */
    struct PeerAddress
    {
        std::uint8_t type = 0U;
        std::uint8_t value[6] = {};
    };

    /** @brief 보안 event가 전달하는 고정 길이 snapshot입니다. */
    struct SecurityEventRecord
    {
        SecurityEvent event = SecurityEvent::error;
        SecurityLevel level = SecurityLevel::none;
        PeerAddress peer = {};
        std::uint32_t passkey = 0U;
        std::uint8_t reason = 0U;
        BondState bond_state = BondState::none;
        bool bonded = false;
    };

    /** @brief Sketch main-thread에서 실행되는 보안 event callback입니다. */
    using SecurityEventCallback = void (*)(const SecurityEventRecord &event,
                                           void *context);

    /** @brief 보안 manager 초기화 계약입니다. */
    struct SecurityConfig
    {
        SecurityLevel minimum_level = SecurityLevel::encrypted;
        bool bonding = true;
        std::uint32_t response_timeout_ms = 30000U;
        SecurityIoCapability io_capability = SecurityIoCapability::keyboard_display;
    };

    /**
     * @brief SMP와 bond를 NUCODE BLE 공통 connection lifecycle 위에서 관리합니다.
     *
     * 이 객체는 Bluetooth stack을 초기화하거나 connection callback을 등록하지 않습니다.
     * BLE 공통 backend가 연결 hook을 전달한 뒤에만 requestSecurity()를 사용할 수 있습니다.
     */
    class SecurityManager final
    {
    public:
        /** @brief SMP callback과 bounded event queue를 초기화합니다. */
        [[nodiscard]] bool begin(const SecurityConfig &config = {}) noexcept;

        /** @brief queued event와 사용자 pairing 응답 timeout을 처리합니다. */
        void poll() noexcept;

        /** @brief 현재 연결에 설정된 최소 security level을 요청합니다. */
        [[nodiscard]] bool requestSecurity() noexcept;

        /** @brief Just Works pairing 요청을 승인하거나 거부합니다. */
        [[nodiscard]] bool acceptPairing(bool accept) noexcept;

        /** @brief passkey input 요청에 000000~999999 값을 제공합니다. */
        [[nodiscard]] bool enterPasskey(std::uint32_t passkey) noexcept;

        /** @brief numeric comparison 결과를 승인하거나 거부합니다. */
        [[nodiscard]] bool confirmPasskey(bool accept) noexcept;

        /** @brief 진행 중인 사용자 pairing 응답을 취소합니다. */
        [[nodiscard]] bool cancelPairing() noexcept;

        /** @brief 현재 identity에 저장된 bond 수를 반환합니다. */
        [[nodiscard]] std::size_t bondCount() const noexcept;

        /** @brief 저장된 peer 주소를 caller buffer에 bounded copy합니다. */
        [[nodiscard]] std::size_t copyBonds(PeerAddress *buffer,
                                            std::size_t capacity) const noexcept;

        /**
         * @brief 지정 peer의 bond 제거 요청을 제출합니다.
         *
         * @return stack이 제거 요청을 수락했으면 true입니다. 실제 영속 삭제 완료를 뜻하지 않습니다.
         */
        [[nodiscard]] bool eraseBond(const PeerAddress &peer) noexcept;

        /**
         * @brief BLE bond 전체 제거 요청을 제출하며 factory reset은 수행하지 않습니다.
         *
         * @return stack이 제거 요청을 수락했으면 true입니다. 실제 영속 삭제 완료를 뜻하지 않습니다.
         */
        [[nodiscard]] bool eraseAllBonds() noexcept;

        /** @brief 현재 연결이 pairing을 완료했는지 반환합니다. */
        [[nodiscard]] bool paired() const noexcept;

        /** @brief 재부팅 뒤 저장 key로 L2 이상 복원까지 검증되었는지 반환합니다. */
        [[nodiscard]] bool bonded() const noexcept;

        /** @brief 현재 연결에서 관찰한 bond 수명주기 상태를 반환합니다. */
        [[nodiscard]] BondState bondState() const noexcept;

        /** @brief 현재 연결에서 관찰한 실제 security level을 반환합니다. */
        [[nodiscard]] SecurityLevel currentLevel() const noexcept;

        /** @brief 사용자 event callback을 등록합니다. */
        void onEvent(SecurityEventCallback callback, void *context = nullptr) noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] SecurityError lastError() const noexcept;

        /** @brief 마지막 Zephyr/NCS 음수 오류를 반환합니다. */
        [[nodiscard]] int lastDriverError() const noexcept;
    };

    /** @brief 표준 Battery Service의 level과 notification을 관리합니다. */
    class BatteryService final
    {
    public:
        /** @brief 0~100% battery level을 갱신하고 구독자에게 알립니다. */
        [[nodiscard]] bool setLevel(std::uint8_t percent) noexcept;

        /** @brief 현재 BAS battery level을 반환합니다. */
        [[nodiscard]] std::uint8_t level() const noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] SecurityError lastError() const noexcept;
    };

    /** @brief Device Information Service에 복사할 bounded 문자열 집합입니다. */
    struct DeviceInformation
    {
        const char *manufacturer = nullptr;
        const char *model = nullptr;
        const char *serial_number = nullptr;
        const char *firmware_revision = nullptr;
        const char *hardware_revision = nullptr;
        const char *software_revision = nullptr;
    };

    /** @brief 표준 DIS 문자열을 runtime settings handler에 안전하게 복사합니다. */
    class DeviceInformationService final
    {
    public:
        /** @brief 모든 필드를 검증한 뒤 DIS cache를 한 번에 갱신합니다. */
        [[nodiscard]] bool configure(const DeviceInformation &information) noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] SecurityError lastError() const noexcept;
    };

    /** @brief USB HID usage ID를 사용하는 8-byte keyboard input report입니다. */
    struct KeyboardReport
    {
        std::uint8_t modifiers = 0U;
        std::uint8_t reserved = 0U;
        std::uint8_t keys[6] = {};
    };

    /** @brief 암호화된 BLE HID keyboard input report를 전송합니다. */
    class HidKeyboard final
    {
    public:
        /** @brief NCS HIDS service와 표준 keyboard report map을 등록합니다. */
        [[nodiscard]] bool begin() noexcept;

        /** @brief 현재 encrypted peer에 하나의 keyboard report를 보냅니다. */
        [[nodiscard]] bool sendReport(const KeyboardReport &report) noexcept;

        /** @brief modifier와 단일 usage를 포함한 key-down report를 보냅니다. */
        [[nodiscard]] bool press(std::uint8_t usage,
                                 std::uint8_t modifiers = 0U) noexcept;

        /** @brief 모든 key를 놓는 zero report를 보냅니다. */
        [[nodiscard]] bool releaseAll() noexcept;

        /** @brief HIDS가 초기화되고 연결된 peer가 있는지 반환합니다. */
        [[nodiscard]] bool connected() const noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] SecurityError lastError() const noexcept;

        /** @brief 마지막 Zephyr/NCS 음수 오류를 반환합니다. */
        [[nodiscard]] int lastDriverError() const noexcept;
    };

}

/** @brief NU54DK의 단일 BLE security manager입니다. */
extern nucode::ble::SecurityManager BLESecurity;

/** @brief NU54DK의 표준 BLE Battery Service facade입니다. */
extern nucode::ble::BatteryService BLEBattery;

/** @brief NU54DK의 표준 BLE Device Information Service facade입니다. */
extern nucode::ble::DeviceInformationService BLEDeviceInformation;

/** @brief NU54DK의 암호화 BLE HID keyboard facade입니다. */
extern nucode::ble::HidKeyboard BLEKeyboard;

#endif
