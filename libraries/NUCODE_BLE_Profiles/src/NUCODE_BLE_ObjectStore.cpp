/** @file @brief OTS object의 할당·범위·권한 검사를 구현합니다.
 * SPDX-License-Identifier: MIT
 */
#include "NUCODE_BLE_ObjectStore.h"

namespace nucode::ble::profiles
{
    ObjectStore::Object *ObjectStore::find(std::uint64_t id) noexcept
    {
        if (id < 0x100U || id > 0xffffffffffffULL)
        {
            return nullptr;
        }
        for (Object &object : objects_)
        {
            if (object.id == id)
            {
                return &object;
            }
        }
        return nullptr;
    }
    const ObjectStore::Object *ObjectStore::find(std::uint64_t id) const noexcept
    {
        return const_cast<ObjectStore *>(this)->find(id);
    }
    ObjectStore::Object *ObjectStore::create(std::uint64_t id, const char *name,
                                             std::size_t capacity, const std::uint8_t *data,
                                             std::size_t length, bool writable,
                                             bool removable) noexcept
    {
        if (id < 0x100U || id > 0xffffffffffffULL || find(id) != nullptr || name == nullptr ||
            capacity == 0U || capacity > maximum_bytes || length > capacity ||
            (data == nullptr && length != 0U))
        {
            return nullptr;
        }
        std::size_t name_length = 0U;
        while (name_length <= maximum_name && name[name_length] != '\0')
        {
            ++name_length;
        }
        if (name_length > maximum_name)
        {
            return nullptr;
        }
        if (name_length != 0U)
        {
            for (const Object &object : objects_)
            {
                bool same = object.id != 0U;
                for (std::size_t i = 0U; i <= name_length && same; ++i)
                {
                    same = object.name[i] == name[i];
                }
                if (same)
                {
                    return nullptr;
                }
            }
        }
        for (Object &object : objects_)
        {
            if (object.id != 0U)
            {
                continue;
            }
            object = Object{};
            object.id = id;
            object.capacity = capacity;
            object.size = length;
            object.writable = writable;
            object.removable = removable;
            for (std::size_t i = 0U; i < name_length; ++i)
            {
                object.name[i] = name[i];
            }
            for (std::size_t i = 0U; i < length; ++i)
            {
                object.bytes[i] = data[i];
            }
            return &object;
        }
        return nullptr;
    }
    bool ObjectStore::erase(std::uint64_t id) noexcept
    {
        Object *object = find(id);
        if (object == nullptr || !object->removable)
        {
            return false;
        }
        *object = Object{};
        return true;
    }
    bool ObjectStore::write(std::uint64_t id, std::size_t offset, const std::uint8_t *data,
                            std::size_t length) noexcept
    {
        Object *object = find(id);
        if (object == nullptr || !object->writable || data == nullptr ||
            offset > object->capacity || length > object->capacity - offset)
        {
            return false;
        }
        for (std::size_t i = 0U; i < length; ++i)
        {
            object->bytes[offset + i] = data[i];
        }
        if (offset + length > object->size)
        {
            object->size = offset + length;
        }
        return true;
    }
    bool ObjectStore::read(std::uint64_t id, std::size_t offset, std::uint8_t *data,
                           std::size_t length) const noexcept
    {
        const Object *object = find(id);
        if (object == nullptr || data == nullptr || offset > object->size ||
            length > object->size - offset)
        {
            return false;
        }
        for (std::size_t i = 0U; i < length; ++i)
        {
            data[i] = object->bytes[offset + i];
        }
        return true;
    }
    std::size_t ObjectStore::count() const noexcept
    {
        std::size_t result = 0U;
        for (const Object &object : objects_)
        {
            if (object.id != 0U)
            {
                ++result;
            }
        }
        return result;
    }
} // namespace nucode::ble::profiles
