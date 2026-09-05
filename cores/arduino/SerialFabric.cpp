/** @file @brief Serial Fabric의 공개 factory와 handle 조회 진입점입니다.
 * SPDX-License-Identifier: MIT
 */
#include <nucode/SerialFabric.h>
#include "internal/serial/SerialFabricInternal.h"
namespace nucode::arduino
{
    using namespace internal::serial;
    SerialPersonality SerialFabricHandle::personality() const noexcept
    {
        return personality_;
    }

    std::uint8_t SerialFabricHandle::instance() const noexcept
    {
        return instance_;
    }

    SerialFabricState SerialFabricHandle::state() const noexcept
    {
        lockFabric();
        const auto value = contextAt(handle_index_).state;
        unlockFabric();
        return value;
    }

    SerialFabricResult SerialFabricHandle::lastResult() const noexcept
    {
        lockFabric();
        const auto value = contextAt(handle_index_).last_result;
        unlockFabric();
        return value;
    }

    int SerialFabricHandle::lastDriverError() const noexcept
    {
        lockFabric();
        const int value = contextAt(handle_index_).last_driver_error;
        unlockFabric();
        return value;
    }

    UarteHandle *SerialFabric::uarte(std::uint8_t instance) noexcept
    {
        static UarteHandle handles[] = {{0U, 0U}, {20U, 1U}, {21U, 2U}, {22U, 3U}, {30U, 4U}};
        const int block = blockIndex(instance);
        return block < 0 ? nullptr : &handles[block];
    }

    SpimHandle *SerialFabric::spim(std::uint8_t instance) noexcept
    {
        static SpimHandle handles[] = {{0U, 5U}, {20U, 6U}, {21U, 7U}, {22U, 8U}, {30U, 9U}};
        const int block = blockIndex(instance);
        return block < 0 ? nullptr : &handles[block];
    }

    SpisHandle *SerialFabric::spis(std::uint8_t instance) noexcept
    {
        static SpisHandle handles[] = {{0U, 10U}, {20U, 11U}, {21U, 12U}, {22U, 13U}, {30U, 14U}};
        const int block = blockIndex(instance);
        return block < 0 ? nullptr : &handles[block];
    }

    TwimHandle *SerialFabric::twim(std::uint8_t instance) noexcept
    {
        static TwimHandle handles[] = {{20U, 15U}, {21U, 16U}, {22U, 17U}, {30U, 18U}};
        const int block = blockIndex(instance);
        return block <= 0 ? nullptr : &handles[block - 1];
    }

    TwisHandle *SerialFabric::twis(std::uint8_t instance) noexcept
    {
        static TwisHandle handles[] = {{20U, 19U}, {21U, 20U}, {22U, 21U}, {30U, 22U}};
        const int block = blockIndex(instance);
        return block <= 0 ? nullptr : &handles[block - 1];
    }

    SerialFabric &serialFabric() noexcept
    {
        static SerialFabric fabric;
        return fabric;
    }
} // namespace nucode::arduino
