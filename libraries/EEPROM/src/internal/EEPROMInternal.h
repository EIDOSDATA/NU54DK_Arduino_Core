/** @file @brief EEPROM mirror와 Settings 저장소의 단일 소유 경계입니다.
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include "EEPROMRecord.h"
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include <errno.h>
#include <string.h>
namespace nucode::eeprom::internal
{
    /** @brief EEPROM singleton의 고정 RAM 상태입니다. */
    struct EEPROMState
    {
        std::uint8_t mirror[EEPROMClass::maximum_size]{};
        std::size_t length{0U};
        bool started{false};
        bool dirty{false};
    };

    EEPROMState &eepromState() noexcept;
    k_mutex &eepromMutex() noexcept;
    atomic_t &lastErrorStorage() noexcept;
    atomic_t &lastDriverErrorStorage() noexcept;
    EEPROMError recordError(EEPROMError error, int driver_error = 0) noexcept;
    EEPROMError recordDriverError(int result) noexcept;
    bool isThreadContext() noexcept;
    bool beginLocked(std::size_t requested_size) noexcept;
    bool commitLocked() noexcept;
    int initializeSettings() noexcept;
} // namespace nucode::eeprom::internal
