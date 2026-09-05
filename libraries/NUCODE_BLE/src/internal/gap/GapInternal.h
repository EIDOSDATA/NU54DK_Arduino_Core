/** @file @brief GAP 내부 상태의 단일 소유와 module 간 경계입니다.
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include <NUCODE_BLE_GAP.h>
#include <internal/NUCODE_BLE_Internal.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/gap.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/net_buf.h>
#include <zephyr/sys/util.h>
#include <string.h>
#include <stdio.h>
namespace nucode::ble::internal::gap
{
    inline constexpr std::size_t maximum_service_uuids = 4U;
    inline constexpr std::size_t maximum_ad_field_data = 29U;
    inline constexpr std::uint16_t minimum_advertising_interval = 0x0020U;
    inline constexpr std::uint16_t maximum_advertising_interval = 0x4000U;
    inline constexpr std::uint16_t default_advertising_interval_min = 0x00a0U;
    inline constexpr std::uint16_t default_advertising_interval_max = 0x00f0U;

    /** @brief callback에서 main thread로 전달하는 작은 GAP event record입니다. */
    struct GapEventRecord
    {
        BLEEvent event;
        std::uint32_t generation;
    };

    /** @brief scan payload와 callback 시작 session을 함께 보존합니다. */
    struct ScanResultRecord
    {
        BLEScanResult result;
        std::uint32_t generation;
    };

    /** @brief legacy advertising의 caller 입력을 고정 buffer에 보존합니다. */
    struct AdvertisingConfiguration
    {
        bool connectable = true;
        bool scan_response_name = true;
        std::uint8_t flags = BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR;
        std::uint16_t interval_min = default_advertising_interval_min;
        std::uint16_t interval_max = default_advertising_interval_max;
        BLEUuid service_uuids[maximum_service_uuids] = {};
        std::size_t service_uuid_count = 0U;
        bool has_manufacturer_data = false;
        std::uint16_t company_id = 0U;
        std::uint8_t manufacturer_data[maximum_ad_field_data] = {};
        std::size_t manufacturer_length = 0U;
        bool has_service_data = false;
        BLEUuid service_data_uuid;
        std::uint8_t service_data[maximum_ad_field_data] = {};
        std::size_t service_data_length = 0U;
    };

    /** @brief software scan filter의 bounded 복사본입니다. */
    struct ScanConfiguration
    {
        bool has_name = false;
        char name[CONFIG_BT_DEVICE_NAME_MAX + 1U] = {};
        bool has_uuid = false;
        BLEUuid uuid;
        bool has_address = false;
        BLEAddress address;
    };

    /** @brief Device session·GAP 상태는 구현 한 곳에서만 생성하며 기존 lock 순서를 따릅니다. */
    struct GapContext
    {
        atomic_t device_initialized = ATOMIC_INIT(0);
        atomic_t advertising_active = ATOMIC_INIT(0);
        atomic_t scanning_active = ATOMIC_INIT(0);
        atomic_t connection_connecting = ATOMIC_INIT(0);
        atomic_t connection_active = ATOMIC_INIT(0);
        atomic_t mtu_exchange_active = ATOMIC_INIT(0);
        atomic_t last_error_value = ATOMIC_INIT(static_cast<atomic_val_t>(BLEError::none));
        atomic_t last_driver_error_value = ATOMIC_INIT(0);
        atomic_t dropped_event_value = ATOMIC_INIT(0);
        atomic_t dropped_scan_value = ATOMIC_INIT(0);
        atomic_t gatt_callback_registered = ATOMIC_INIT(0);
        atomic_t device_session_generation = ATOMIC_INIT(1);

        struct k_spinlock connection_lock;
        struct k_spinlock configuration_lock;
        struct bt_conn *active_connection = nullptr;
        struct bt_conn *pending_connection = nullptr;
        std::uint32_t active_connection_generation = 0U;
        std::uint32_t pending_connection_generation = 0U;

        char local_name[CONFIG_BT_DEVICE_NAME_MAX + 1U] = {};
        BLEAddress last_peer_address;

        BLEEventCallback event_callback = nullptr;
        void *event_context = nullptr;
        BLEScanCallback scan_callback = nullptr;
        void *scan_context = nullptr;

        struct bt_gatt_exchange_params mtu_exchange_parameters = {};
    };
    GapContext &gapState() noexcept;
    k_msgq &gapEventQueue() noexcept;
    k_msgq &scanResultQueue() noexcept;
    void lockGapLifecycle() noexcept;
    void unlockGapLifecycle() noexcept;
    bt_gatt_cb &gattCallbacks() noexcept;
    bt_conn *referenceActiveConnection() noexcept;
    void queueEvent(BLEEvent event, std::uint32_t generation = 0U) noexcept;

    /** @brief local name의 UTF-8이 well-formed인지 동적 할당 없이 검증합니다. */
    inline bool validUtf8(const char *text, std::size_t length) noexcept
    {
        std::size_t index = 0U;
        while (index < length)
        {
            const auto first = static_cast<std::uint8_t>(text[index]);
            if (first <= 0x7fU)
            {
                ++index;
                continue;
            }

            std::size_t continuation_count = 0U;
            std::uint32_t code_point = 0U;
            std::uint32_t minimum = 0U;
            if ((first & 0xe0U) == 0xc0U)
            {
                continuation_count = 1U;
                code_point = first & 0x1fU;
                minimum = 0x80U;
            }
            else if ((first & 0xf0U) == 0xe0U)
            {
                continuation_count = 2U;
                code_point = first & 0x0fU;
                minimum = 0x800U;
            }
            else if ((first & 0xf8U) == 0xf0U)
            {
                continuation_count = 3U;
                code_point = first & 0x07U;
                minimum = 0x10000U;
            }
            else
            {
                return false;
            }
            if (index + continuation_count >= length)
            {
                return false;
            }
            for (std::size_t offset = 1U; offset <= continuation_count; ++offset)
            {
                const auto next = static_cast<std::uint8_t>(text[index + offset]);
                if ((next & 0xc0U) != 0x80U)
                {
                    return false;
                }
                code_point = (code_point << 6U) | (next & 0x3fU);
            }
            if (code_point < minimum || code_point > 0x10ffffU ||
                (code_point >= 0xd800U && code_point <= 0xdfffU))
            {
                return false;
            }
            index += continuation_count + 1U;
        }
        return true;
    }

    /** @brief thread 전용 공개 API가 ISR에서 호출되지 않았는지 검사합니다. */
    inline bool requireThreadContext() noexcept
    {
        return nucode::ble::internal::requireThreadContext();
    }

    /** @brief 공개 주소를 Zephyr LE 주소로 변환합니다. */
    inline bool toZephyrAddress(const BLEAddress &source, bt_addr_le_t &destination) noexcept
    {
        if (!source.valid())
        {
            return false;
        }
        destination.type = source.type() == BLEAddress::Type::public_address ? BT_ADDR_LE_PUBLIC
                                                                             : BT_ADDR_LE_RANDOM;
        ::memcpy(destination.a.val, source.data(), sizeof(destination.a.val));
        return true;
    }

    /** @brief Zephyr LE 주소를 callback 밖 수명의 공개 주소로 복사합니다. */
    inline BLEAddress fromZephyrAddress(const bt_addr_le_t &source) noexcept
    {
        const bool public_type =
            source.type == BT_ADDR_LE_PUBLIC || source.type == BT_ADDR_LE_PUBLIC_ID;
        return BLEAddress(source.a.val, public_type ? BLEAddress::Type::public_address
                                                    : BLEAddress::Type::random_address);
    }
} // namespace nucode::ble::internal::gap
