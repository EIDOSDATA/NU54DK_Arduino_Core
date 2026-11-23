/** @file @brief native profile adapter의 공개 BLE 연결 경계를 제어합니다. */
#pragma once
#include <cstdint>
#include <cstddef>
namespace nucode::ble
{
    struct BLEConnectionHandle
    {
        std::uint32_t generation = 0U;
        bool valid() const
        {
            return generation != 0U;
        }
        bool operator==(BLEConnectionHandle other) const
        {
            return generation == other.generation;
        }
    };
} // namespace nucode::ble
struct ProfileMockDevice
{
    bool initialized() const
    {
        return true;
    }
};
struct ProfileMockConnection
{
    nucode::ble::BLEConnectionHandle peer;
    bool live = false;
    unsigned disconnects = 0U;
    bool connected(nucode::ble::BLEConnectionHandle handle) const
    {
        return live && peer == handle;
    }
    std::size_t count() const
    {
        return live ? 1U : 0U;
    }
    bool disconnect(nucode::ble::BLEConnectionHandle handle)
    {
        if (!connected(handle))
        {
            return false;
        }
        ++disconnects;
        return true;
    }
};
inline ProfileMockDevice BLEDevice;
inline ProfileMockConnection BLEConnection;
