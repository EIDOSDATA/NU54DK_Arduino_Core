/** @file @brief 고정 파일 slot의 참조·generation·오류와 mutex를 단일 소유합니다.
 * SPDX-License-Identifier: MIT
 */
#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include "StorageInternal.h"
namespace nucode::littlefs::internal
{
    namespace
    {
        K_MUTEX_DEFINE(filesystem_mutex);
        FileSystemState state{};
        FileSlots slots{};
    } // namespace
    FileSystemState &filesystemState() noexcept
    {
        return state;
    }
    FileSlots &fileSlots() noexcept
    {
        return slots;
    }
    k_mutex &filesystemMutex() noexcept
    {
        return filesystem_mutex;
    }
    /** @brief 마지막 공개 오류와 원래 driver 오류를 함께 기록합니다. */
    FSError recordError(FSError error, int driver_error) noexcept
    {
        atomic_set(&filesystemState().last_error_value, static_cast<atomic_val_t>(error));
        atomic_set(&filesystemState().last_driver_error_value,
                   static_cast<atomic_val_t>(driver_error));
        return error;
    }

    /** @brief Zephyr filesystem 오류를 공개 분류로 변환합니다. */
    FSError recordDriverError(int result) noexcept
    {
        switch (result)
        {
        case -EINVAL:
            return recordError(FSError::invalid_argument, result);
        case -ENOENT:
            return recordError(FSError::not_found, result);
        case -EEXIST:
            return recordError(FSError::already_exists, result);
        case -EBUSY:
        case -EAGAIN:
        case -EMFILE:
            return recordError(FSError::busy, result);
        case -ENOSPC:
        case -ENOMEM:
            return recordError(FSError::no_space, result);
        case -EILSEQ:
        case -EBADMSG:
            return recordError(FSError::corrupt, result);
        default:
            return recordError(FSError::driver_error, result);
        }
    }

    /** @brief blocking filesystem API를 thread 문맥으로 제한합니다. */
    bool isThreadContext() noexcept
    {
        if (k_is_in_isr())
        {
            recordError(FSError::invalid_context, -EWOULDBLOCK);
            return false;
        }
        return true;
    }

    /** @brief filesystem_mutex를 보유한 호출자가 slot과 generation의 유효성을 검사합니다. */
    FileSlot *validSlot(std::uint8_t slot, std::uint32_t generation) noexcept
    {
        return slot < maximum_open_files && fileSlots()[slot].active &&
                       fileSlots()[slot].generation == generation
                   ? &fileSlots()[slot]
                   : nullptr;
    }

    /** @brief filesystemMutex() 아래에서 유효한 공유 slot의 참조를 하나 추가합니다. */
    bool retainSlotLocked(std::uint8_t index, std::uint32_t generation) noexcept
    {
        FileSlot *slot = validSlot(index, generation);
        if (slot == nullptr)
        {
            return false;
        }
        if (slot->references == UINT16_MAX)
        {
            recordError(FSError::busy, -EMFILE);
            return false;
        }
        ++slot->references;
        return true;
    }

    /** @brief filesystemMutex() 아래에서 참조를 줄이고 마지막 참조만 backend를 닫습니다. */
    void releaseSlotLocked(std::uint8_t index, std::uint32_t generation) noexcept
    {
        FileSlot *slot = validSlot(index, generation);
        if (slot == nullptr)
        {
            return;
        }
        if (slot->references > 1U)
        {
            --slot->references;
            recordError(FSError::none);
            return;
        }
        const int result = fs_close(&slot->file);
        slot->references = 0U;
        slot->active = false;
        slot->path[0] = '\0';
        if (result < 0)
        {
            recordDriverError(result);
        }
        else
        {
            recordError(FSError::none);
        }
    }

    /** @brief 열린 파일이 하나라도 있는지 반환합니다. */
    bool hasOpenFiles() noexcept
    {
        for (const FileSlot &slot : fileSlots())
        {
            if (slot.active)
            {
                return true;
            }
        }
        return false;
    }
} // namespace nucode::littlefs::internal
#endif
