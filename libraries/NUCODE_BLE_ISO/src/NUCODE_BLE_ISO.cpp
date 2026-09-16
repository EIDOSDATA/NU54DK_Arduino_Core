/**
 * @file NUCODE_BLE_ISO.cpp
 * @brief NU54DK Bluetooth LE Isochronous Channels 공개 API를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "NUCODE_BLE_ISO.h"

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)

#if defined(CONFIG_NUCODE_BLE_ISO_MODE_CIS_CENTRAL)
#define NUCODE_BLE_ISO_RAW_CIS
#elif defined(CONFIG_NUCODE_BLE_ISO_MODE_CIS_PERIPHERAL)
#define NUCODE_BLE_ISO_RAW_CIS
#elif defined(CONFIG_NUCODE_BLE_ISO_MODE_CIS_TO_BIS_PEER)
#define NUCODE_BLE_ISO_CIS_ROLE "peripheral"
#define NUCODE_BLE_ISO_CIS_TO_BIS_PEER
#include "internal/NUCODE_ISO_CIS_Impl.inc"
#elif defined(CONFIG_NUCODE_BLE_ISO_MODE_BIS_SOURCE)
#define NUCODE_BLE_ISO_RAW_BIS
#elif defined(CONFIG_NUCODE_BLE_ISO_MODE_BIS_RECEIVER) || \
    defined(CONFIG_NUCODE_BLE_ISO_MODE_CIS_TO_BIS_RECEIVER)
#if defined(CONFIG_NUCODE_BLE_ISO_MODE_BIS_RECEIVER)
#define NUCODE_BLE_ISO_RAW_BIS
#else
#define NUCODE_BLE_ISO_BIS_ROLE "receiver"
#include "internal/NUCODE_ISO_BIS_Impl.inc"
#endif
#elif defined(CONFIG_NUCODE_BLE_ISO_MODE_BIS_ENCRYPTED_SOURCE)
#define NUCODE_BLE_ISO_BIS_ROLE "source"
#define NUCODE_BLE_ISO_BIS_ENCRYPTED
#include "internal/NUCODE_ISO_BIS_Impl.inc"
#elif defined(CONFIG_NUCODE_BLE_ISO_MODE_BIS_ENCRYPTED_RECEIVER)
#define NUCODE_BLE_ISO_BIS_ROLE "receiver"
#define NUCODE_BLE_ISO_BIS_ENCRYPTED
#include "internal/NUCODE_ISO_BIS_Impl.inc"
#elif defined(CONFIG_NUCODE_BLE_ISO_MODE_BIS_TIME_SOURCE)
#define NUCODE_BLE_ISO_BIS_ROLE "source"
#define NUCODE_BLE_ISO_BIS_TIME_SYNC
#include "internal/NUCODE_ISO_BIS_Impl.inc"
#elif defined(CONFIG_NUCODE_BLE_ISO_MODE_BIS_TIME_RECEIVER)
#define NUCODE_BLE_ISO_BIS_ROLE "receiver"
#define NUCODE_BLE_ISO_BIS_TIME_SYNC
#include "internal/NUCODE_ISO_BIS_Impl.inc"
#elif defined(CONFIG_NUCODE_BLE_ISO_MODE_CIS_TO_BIS_BRIDGE)
#include "internal/NUCODE_ISO_Combined_Impl.inc"
#else
#error "NUCODE BLE ISO 역할이 Kconfig에 선택되지 않았습니다."
#endif

namespace nucode::ble::iso
{
    /** @brief 선택된 backend와 공개 역할을 연결합니다. */
    Role Program::configuredRole() noexcept
    {
#if defined(CONFIG_NUCODE_BLE_ISO_MODE_CIS_CENTRAL)
        return Role::cis_central;
#elif defined(CONFIG_NUCODE_BLE_ISO_MODE_CIS_PERIPHERAL)
        return Role::cis_peripheral;
#elif defined(CONFIG_NUCODE_BLE_ISO_MODE_CIS_TO_BIS_PEER)
        return Role::cis_to_bis_peer;
#elif defined(CONFIG_NUCODE_BLE_ISO_MODE_BIS_SOURCE)
        return Role::bis_source;
#elif defined(CONFIG_NUCODE_BLE_ISO_MODE_BIS_RECEIVER)
        return Role::bis_receiver;
#elif defined(CONFIG_NUCODE_BLE_ISO_MODE_BIS_ENCRYPTED_SOURCE)
        return Role::bis_encrypted_source;
#elif defined(CONFIG_NUCODE_BLE_ISO_MODE_BIS_ENCRYPTED_RECEIVER)
        return Role::bis_encrypted_receiver;
#elif defined(CONFIG_NUCODE_BLE_ISO_MODE_BIS_TIME_SOURCE)
        return Role::bis_time_source;
#elif defined(CONFIG_NUCODE_BLE_ISO_MODE_BIS_TIME_RECEIVER)
        return Role::bis_time_receiver;
#elif defined(CONFIG_NUCODE_BLE_ISO_MODE_CIS_TO_BIS_BRIDGE)
        return Role::cis_to_bis_bridge;
#else
        return Role::cis_to_bis_receiver;
#endif
    }

    /** @brief 역할 일치 여부를 확인한 뒤 내부 Zephyr backend를 시작합니다. */
    Error Program::begin() noexcept
    {
#if defined(NUCODE_BLE_ISO_RAW_CIS) || defined(NUCODE_BLE_ISO_RAW_BIS)
        last_error_ = Error::not_ready;
        return last_error_;
#else
        if (role_ != configuredRole())
        {
            last_error_ = Error::configuration_mismatch;
            return last_error_;
        }
        internal::begin();
        started_ = true;
        last_error_ = Error::none;
        return last_error_;
#endif
    }

    /** @brief 시작된 backend의 bounded main-thread 작업을 실행합니다. */
    Error Program::poll() noexcept
    {
#if defined(NUCODE_BLE_ISO_RAW_CIS) || defined(NUCODE_BLE_ISO_RAW_BIS)
        last_error_ = Error::not_ready;
        return last_error_;
#else
        if (!started_)
        {
            last_error_ = Error::not_started;
            return last_error_;
        }
        internal::poll();
        last_error_ = Error::none;
        return last_error_;
#endif
    }
}

#endif
