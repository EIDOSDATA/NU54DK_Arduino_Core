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
#if !defined(CONFIG_NUCODE_BLE_PERIODIC_REPORT_QUEUE_SIZE)
#define CONFIG_NUCODE_BLE_PERIODIC_REPORT_QUEUE_SIZE 8
#endif
#if !defined(CONFIG_NUCODE_BLE_PAWR_RESPONSE_QUEUE_SIZE)
#define CONFIG_NUCODE_BLE_PAWR_RESPONSE_QUEUE_SIZE 8
#endif
namespace nucode::ble::internal
{
    /** @brief 공개 handle의 token 표현을 GAP 내부에만 개방합니다. */
    struct BLEConnectionHandleAccess
    {
        [[nodiscard]] static constexpr BLEConnectionHandle make(std::size_t slot,
                                                                std::uint32_t generation) noexcept
        {
            return generation == 0U
                       ? BLEConnectionHandle{}
                       : BLEConnectionHandle((static_cast<std::uint64_t>(generation) << 8U) |
                                             static_cast<std::uint64_t>(slot + 1U));
        }

        [[nodiscard]] static constexpr std::size_t slot(BLEConnectionHandle handle) noexcept
        {
            const std::uint64_t encoded = handle.token_ & 0xffU;
            return encoded == 0U ? static_cast<std::size_t>(0xffU)
                                 : static_cast<std::size_t>(encoded - 1U);
        }

        [[nodiscard]] static constexpr std::uint32_t generation(
            BLEConnectionHandle handle) noexcept
        {
            return static_cast<std::uint32_t>(handle.token_ >> 8U);
        }

        [[nodiscard]] static constexpr BLEAdvertisingSetHandle makeAdvertisingSet(
            std::uint32_t generation) noexcept
        {
            return BLEAdvertisingSetHandle(generation);
        }

        [[nodiscard]] static constexpr std::uint32_t generation(
            BLEAdvertisingSetHandle handle) noexcept
        {
            return handle.token_;
        }

        [[nodiscard]] static constexpr BLEPeriodicSyncHandle makePeriodicSync(
            std::uint32_t generation) noexcept
        {
            return BLEPeriodicSyncHandle(generation);
        }

        [[nodiscard]] static constexpr std::uint32_t generation(
            BLEPeriodicSyncHandle handle) noexcept
        {
            return handle.token_;
        }
    };
} // namespace nucode::ble::internal
namespace nucode::ble::internal::gap
{
    inline constexpr std::size_t maximum_connection_slots = 2U;
    inline constexpr std::size_t central_connection_slot = 0U;
    inline constexpr std::size_t peripheral_connection_slot = 1U;
    inline constexpr std::size_t maximum_mtu_exchange_contexts = 4U;
    inline constexpr std::size_t maximum_service_uuids = 4U;
    inline constexpr std::size_t maximum_ad_field_data = 29U;
    inline constexpr std::uint16_t minimum_advertising_interval = 0x0020U;
    inline constexpr std::uint16_t maximum_advertising_interval = 0x4000U;
    inline constexpr std::uint16_t default_advertising_interval_min = 0x00a0U;
    inline constexpr std::uint16_t default_advertising_interval_max = 0x00f0U;

    /** @brief callback에서 main thread로 전달하는 작은 GAP event record입니다. */
    struct GapEventRecord
    {
        BLEEventInfo information;
        std::uint32_t device_generation;
    };

    /** @brief 역할이 고정된 한 connection slot의 ref와 generation입니다. */
    struct ConnectionSlot
    {
        explicit ConnectionSlot(BLELinkRole assigned_role = BLELinkRole::none) noexcept
            : role(assigned_role)
        {
        }

        struct bt_conn *active = nullptr;
        struct bt_conn *pending = nullptr;
        std::uint32_t generation = 0U;
        std::uint32_t device_generation = 0U;
        BLEAddress peer_address;
        BLEAddress connection_address;
        bool identity_resolved = false;
        BLELinkRole role = BLELinkRole::none;
    };

    /** @brief 늦은 MTU callback이 재사용 slot로 들어가지 않게 요청 token을 보존합니다. */
    struct MtuExchangeContext
    {
        struct bt_gatt_exchange_params parameters = {};
        BLEConnectionHandle connection;
        atomic_t active = ATOMIC_INIT(0);
    };

    /** @brief 한 개 고정 extended advertising set의 generation과 payload입니다. */
    struct ExtendedAdvertisingContext
    {
        struct bt_le_ext_adv *instance = nullptr;
        std::uint32_t generation = 0U;
        std::uint32_t device_generation = 0U;
        atomic_t active = ATOMIC_INIT(0);
        bool connectable = false;
        bool scannable = false;
        std::uint8_t advertising_data[ExtendedAdvertising::maximum_payload_length] = {};
        std::size_t advertising_length = 0U;
        std::uint8_t scan_response_data[ExtendedAdvertising::maximum_payload_length] = {};
        std::size_t scan_response_length = 0U;
    };

    /** @brief scan payload와 callback 시작 session을 함께 보존합니다. */
    struct ScanResultRecord
    {
        BLEScanResult result;
        std::uint32_t generation;
    };

    /** @brief periodic advertiser가 결합된 extended set과 고정 payload입니다. */
    struct PeriodicAdvertisingContext
    {
        BLEAdvertisingSetHandle advertising_set;
        atomic_t configured = ATOMIC_INIT(0);
        atomic_t active = ATOMIC_INIT(0);
        std::uint8_t data[PeriodicAdvertising::maximum_payload_length] = {};
        std::size_t length = 0U;
    };

    /** @brief 한 개 periodic sync object의 generation과 session입니다. */
    struct PeriodicSyncContext
    {
        struct bt_le_per_adv_sync *instance = nullptr;
        std::uint32_t generation = 0U;
        std::uint32_t device_generation = 0U;
        atomic_t synchronized = ATOMIC_INIT(0);
        BLEAddress address;
        std::uint8_t sid = 0xffU;
    };

    /** @brief periodic report와 callback 시작 session을 함께 보존합니다. */
    struct PeriodicReportRecord
    {
        BLEPeriodicReport report;
        std::uint32_t device_generation;
    };

    /** @brief 한 PAwR subevent의 사전 복사된 payload와 response window입니다. */
    struct PawrSubeventContext
    {
        std::uint8_t data[Pawr::maximum_payload_length] = {};
        std::uint16_t length = 0U;
        std::uint8_t response_slot_start = 0U;
        std::uint8_t response_slot_count = 0U;
        bool configured = false;
    };

    /** @brief bounded PAwR advertiser의 set과 subevent storage입니다. */
    struct PawrContext
    {
        BLEAdvertisingSetHandle advertising_set;
        std::uint8_t subevent_count = 0U;
        std::uint8_t response_slot_count = 0U;
        bool configured = false;
        PawrSubeventContext subevents[Pawr::maximum_subevents] = {};
    };

    /** @brief PAwR response와 callback 시작 session을 함께 보존합니다. */
    struct PawrResponseRecord
    {
        BLEPawrResponse response;
        std::uint32_t device_generation;
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
        atomic_t dropped_periodic_report_value = ATOMIC_INIT(0);
        atomic_t dropped_pawr_response_value = ATOMIC_INIT(0);
        atomic_t gatt_callback_registered = ATOMIC_INIT(0);
        atomic_t scan_callback_registered = ATOMIC_INIT(0);
        atomic_t device_session_generation = ATOMIC_INIT(1);
        atomic_t next_advertising_generation = ATOMIC_INIT(1);
        atomic_t next_periodic_sync_generation = ATOMIC_INIT(1);
        atomic_t periodic_sync_callback_registered = ATOMIC_INIT(0);
        atomic_t rpa_expiration_count = ATOMIC_INIT(0);
        atomic_t rpa_rotation_timeout = ATOMIC_INIT(900);

        struct k_spinlock connection_lock;
        struct k_spinlock configuration_lock;
        ConnectionSlot connection_slots[maximum_connection_slots] = {
            ConnectionSlot(BLELinkRole::central),
            ConnectionSlot(BLELinkRole::peripheral),
        };
        atomic_t next_connection_generation = ATOMIC_INIT(1);

        char local_name[CONFIG_BT_DEVICE_NAME_MAX + 1U] = {};
        BLEAddress last_central_address;

        BLEEventCallback event_callback = nullptr;
        void *event_context = nullptr;
        BLEEventInfoCallback event_info_callback = nullptr;
        void *event_info_context = nullptr;
        BLEScanCallback scan_callback = nullptr;
        void *scan_context = nullptr;
        BLEPeriodicReportCallback periodic_report_callback = nullptr;
        void *periodic_report_context = nullptr;
        BLEConnectionHandle past_subscriptions[maximum_connection_slots] = {};
        BLEPawrResponseCallback pawr_response_callback = nullptr;
        void *pawr_response_context = nullptr;

        MtuExchangeContext mtu_exchange_contexts[maximum_mtu_exchange_contexts] = {};
        ExtendedAdvertisingContext extended_advertising;
        PeriodicAdvertisingContext periodic_advertising;
        PeriodicSyncContext periodic_sync;
        PawrContext pawr;
    };
    GapContext &gapState() noexcept;
    k_msgq &gapEventQueue() noexcept;
    k_msgq &scanResultQueue() noexcept;
    k_msgq &periodicReportQueue() noexcept;
    k_msgq &pawrResponseQueue() noexcept;
    void lockGapLifecycle() noexcept;
    void unlockGapLifecycle() noexcept;
    bt_gatt_cb &gattCallbacks() noexcept;
    bt_conn *referenceConnection(BLEConnectionHandle connection) noexcept;
    bt_conn *referenceLegacyConnection() noexcept;
    bool extendedAdvertisingExists() noexcept;
    bool currentAdvertisingSet(BLEAdvertisingSetHandle handle,
                               struct bt_le_ext_adv *&instance,
                               std::uint32_t &device_generation) noexcept;
    bool periodicAdvertisingUsesSet(BLEAdvertisingSetHandle handle) noexcept;
    void releasePeriodicAdvertisingSet(BLEAdvertisingSetHandle handle) noexcept;
    bool currentPeriodicSync(BLEPeriodicSyncHandle handle,
                             struct bt_le_per_adv_sync *&instance,
                             std::uint32_t &device_generation) noexcept;
    void pawrDataRequested(struct bt_le_ext_adv *advertiser,
                           const struct bt_le_per_adv_data_request *request) noexcept;
    void pawrResponseReceived(struct bt_le_ext_adv *advertiser,
                              struct bt_le_per_adv_response_info *information,
                              struct net_buf_simple *buffer) noexcept;
    void releasePawrSet(BLEAdvertisingSetHandle handle) noexcept;
    void endExtendedAdvertising() noexcept;
    void endPeriodicAdvertising() noexcept;
    void endPawr() noexcept;
    void queueEvent(BLEEvent event, BLEConnectionHandle connection = {},
                    BLELinkRole role = BLELinkRole::none,
                    std::uint32_t device_generation = 0U,
                    BLEAdvertisingSetHandle advertising_set = {},
                    BLEPeriodicSyncHandle periodic_sync = {}) noexcept;

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
