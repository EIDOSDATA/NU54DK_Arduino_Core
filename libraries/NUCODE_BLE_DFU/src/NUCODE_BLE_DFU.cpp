/**
 * @file NUCODE_BLE_DFU.cpp
 * @brief MCUboot image 상태와 명시적 confirm을 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_DFU.h>

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)

#include <zephyr/dfu/mcuboot.h>
#include <zephyr/storage/flash_map.h>

namespace nucode::ble
{

    bool SecureDfuManager::begin() noexcept
    {
        struct mcuboot_img_header header = {};
        const int result = boot_read_bank_header(
            PARTITION_ID(slot0_partition), &header, sizeof(header));
        if ((result != 0) || (header.mcuboot_version != 1U))
        {
            initialized_ = false;
            error_ = SecureDfuError::invalid_image;
            driver_error_ = result;
            return false;
        }
        version_.major = header.h.v1.sem_ver.major;
        version_.minor = header.h.v1.sem_ver.minor;
        version_.revision = header.h.v1.sem_ver.revision;
        version_.build = header.h.v1.sem_ver.build_num;
        active_slot_ = static_cast<std::uint8_t>(boot_fetch_active_slot());
        initialized_ = true;
        error_ = SecureDfuError::none;
        driver_error_ = 0;
        return true;
    }

    bool SecureDfuManager::confirm() noexcept
    {
        if (!initialized_)
        {
            error_ = SecureDfuError::not_initialized;
            driver_error_ = 0;
            return false;
        }
        const int result = boot_write_img_confirmed();
        if (result != 0)
        {
            error_ = SecureDfuError::driver_error;
            driver_error_ = result;
            return false;
        }
        error_ = SecureDfuError::none;
        driver_error_ = 0;
        return true;
    }

    bool SecureDfuManager::confirmed() const noexcept
    {
        return initialized_ && boot_is_img_confirmed();
    }

    std::uint8_t SecureDfuManager::activeSlot() const noexcept
    {
        return active_slot_;
    }

    SecureDfuImageVersion SecureDfuManager::version() const noexcept
    {
        return version_;
    }

    BLEUuid SecureDfuManager::serviceUuid() noexcept
    {
        return BLEUuid("8d53dc1d-1db7-4cd3-868b-8a527460aa84");
    }

    SecureDfuError SecureDfuManager::lastError() const noexcept
    {
        return error_;
    }

    int SecureDfuManager::lastDriverError() const noexcept
    {
        return driver_error_;
    }

} // namespace nucode::ble

nucode::ble::SecureDfuManager BLESecureDfu;

#endif
