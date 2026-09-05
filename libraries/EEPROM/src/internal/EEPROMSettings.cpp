/** @file @brief 고정 EEPROM mirror와 Settings load/save의 수명주기입니다.
 * SPDX-License-Identifier: MIT
 */
#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include "EEPROMInternal.h"
#include <zephyr/settings/settings.h>
namespace nucode::eeprom::internal
{
    namespace
    {
        K_MUTEX_DEFINE(eeprom_mutex);
        EEPROMState state{};
        atomic_t last_error_value = ATOMIC_INIT(static_cast<atomic_val_t>(EEPROMError::none));
        atomic_t last_driver_error_value = ATOMIC_INIT(0);
    } // namespace
    EEPROMState &eepromState() noexcept
    {
        return state;
    }
    k_mutex &eepromMutex() noexcept
    {
        return eeprom_mutex;
    }
    atomic_t &lastErrorStorage() noexcept
    {
        return last_error_value;
    }
    atomic_t &lastDriverErrorStorage() noexcept
    {
        return last_driver_error_value;
    }
    int initializeSettings() noexcept
    {
        return settings_subsys_init();
    }
    /** @brief 마지막 공개 오류와 원래 driver 오류를 함께 기록합니다. */
    EEPROMError recordError(EEPROMError error, int driver_error) noexcept
    {
        atomic_set(&last_error_value, static_cast<atomic_val_t>(error));
        atomic_set(&last_driver_error_value, static_cast<atomic_val_t>(driver_error));
        return error;
    }

    /** @brief Settings/ZMS 오류를 공개 EEPROM 오류로 변환합니다. */
    EEPROMError recordDriverError(int result) noexcept
    {
        if (result == -ENOSPC || result == -ENOMEM)
        {
            return recordError(EEPROMError::no_space, result);
        }
        if (result == -EINVAL)
        {
            return recordError(EEPROMError::invalid_argument, result);
        }
        return recordError(EEPROMError::driver_error, result);
    }

    /** @brief blocking storage API를 thread 문맥으로 제한합니다. */
    bool isThreadContext() noexcept
    {
        if (k_is_in_isr())
        {
            recordError(EEPROMError::invalid_context, -EWOULDBLOCK);
            return false;
        }
        return true;
    }

    /** @brief 호출자가 mutex를 가진 상태에서 저장소 record를 검증해 엽니다. */
    bool beginLocked(std::size_t requested_size) noexcept
    {
        if (requested_size == 0U || requested_size > EEPROMClass::maximum_size)
        {
            recordError(EEPROMError::invalid_argument, -EINVAL);
            return false;
        }

        if (state.started)
        {
            if (state.length != requested_size)
            {
                if (requested_size > state.length)
                {
                    memset(state.mirror + state.length, 0xff, requested_size - state.length);
                }
                state.length = requested_size;
                state.dirty = true;
            }
            recordError(EEPROMError::none);
            return true;
        }

        const int initialized = settings_subsys_init();
        if (initialized != 0)
        {
            recordDriverError(initialized);
            return false;
        }

        const ssize_t stored_size = settings_get_val_len(settings_key);
        if (stored_size == -ENOENT)
        {
            memset(state.mirror, 0xff, requested_size);
            state.length = requested_size;
            state.started = true;
            state.dirty = false;
            recordError(EEPROMError::none);
            return true;
        }
        if (stored_size < 0)
        {
            recordDriverError(static_cast<int>(stored_size));
            return false;
        }
        if (stored_size < static_cast<ssize_t>(record_header_size + 1U) ||
            stored_size > static_cast<ssize_t>(record_header_size + EEPROMClass::maximum_size))
        {
            recordError(EEPROMError::corrupt, -EBADMSG);
            return false;
        }

        std::uint8_t record[record_header_size + EEPROMClass::maximum_size]{};
        const ssize_t loaded = settings_load_one(settings_key, record, sizeof(record));
        if (loaded < 0)
        {
            recordDriverError(static_cast<int>(loaded));
            return false;
        }
        const std::uint32_t magic = loadInteger<std::uint32_t>(&record[0]);
        const std::uint16_t version = loadInteger<std::uint16_t>(&record[4]);
        const std::uint16_t stored_length = loadInteger<std::uint16_t>(&record[6]);
        const std::uint32_t expected_crc = loadInteger<std::uint32_t>(&record[8]);
        if (loaded != static_cast<ssize_t>(record_header_size + stored_length) ||
            magic != record_magic || version != record_version || stored_length == 0U ||
            stored_length > EEPROMClass::maximum_size ||
            crc32(record + record_header_size, stored_length) != expected_crc)
        {
            recordError(EEPROMError::corrupt, -EBADMSG);
            return false;
        }

        const std::size_t copied = requested_size < stored_length ? requested_size : stored_length;
        memcpy(state.mirror, record + record_header_size, copied);
        if (requested_size > copied)
        {
            memset(state.mirror + copied, 0xff, requested_size - copied);
        }
        state.length = requested_size;
        state.started = true;
        state.dirty = requested_size != stored_length;
        recordError(EEPROMError::none);
        return true;
    }

    /** @brief 호출자가 mutex를 가진 상태에서 dirty mirror를 원자 record로 저장합니다. */
    bool commitLocked() noexcept
    {
        if (!state.started)
        {
            recordError(EEPROMError::not_started, -EACCES);
            return false;
        }
        if (!state.dirty)
        {
            recordError(EEPROMError::none);
            return true;
        }

        std::uint8_t record[record_header_size + EEPROMClass::maximum_size]{};
        storeInteger<std::uint32_t>(&record[0], record_magic);
        storeInteger<std::uint16_t>(&record[4], record_version);
        storeInteger<std::uint16_t>(&record[6], static_cast<std::uint16_t>(state.length));
        storeInteger<std::uint32_t>(&record[8], crc32(state.mirror, state.length));
        memcpy(record + record_header_size, state.mirror, state.length);
        const int result =
            settings_save_one(settings_key, record, record_header_size + state.length);
        if (result != 0)
        {
            recordDriverError(result);
            return false;
        }
        state.dirty = false;
        recordError(EEPROMError::none);
        return true;
    }
} // namespace nucode::eeprom::internal
#endif
