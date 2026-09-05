/** @file @brief Stream 공개 factory와 기존 family 잠금·IRQ 초기화 진입점입니다.
 * SPDX-License-Identifier: MIT
 */
#include "internal/stream/StreamFabricInternal.h"
namespace nucode::arduino
{
    using namespace internal::stream;
    namespace
    {
        K_MUTEX_DEFINE(stream_fabric_mutex);
        k_spinlock dma_metadata_lock{};
        int connectStreamFabricIrqs()
        {
            IRQ_CONNECT(PDM20_IRQn, IRQ_PRIO_LOWEST, pdm20Irq, nullptr, 0);
            IRQ_CONNECT(PDM21_IRQn, IRQ_PRIO_LOWEST, pdm21Irq, nullptr, 0);
            IRQ_CONNECT(I2S20_IRQn, IRQ_PRIO_LOWEST, i2s20Irq, nullptr, 0);
            IRQ_CONNECT(QDEC20_IRQn, IRQ_PRIO_LOWEST, qdec20Irq, nullptr, 0);
            IRQ_CONNECT(QDEC21_IRQn, IRQ_PRIO_LOWEST, qdec21Irq, nullptr, 0);
            return 0;
        }
        SYS_INIT(connectStreamFabricIrqs, APPLICATION, CONFIG_APPLICATION_INIT_PRIORITY);
    } // namespace
    PdmFabric *StreamFabric::pdm(std::uint8_t instance) noexcept
    {
        static PdmFabric handles[]{PdmFabric(20U), PdmFabric(21U)};
        for (auto &handle : handles)
        {
            if (handle.instance() == instance)
            {
                return &handle;
            }
        }
        return nullptr;
    }

    I2sFabric *StreamFabric::i2s(std::uint8_t instance) noexcept
    {
        static I2sFabric handle;
        return instance == 20U ? &handle : nullptr;
    }

    QdecFabric *StreamFabric::qdec(std::uint8_t instance) noexcept
    {
        static QdecFabric handles[]{QdecFabric(20U), QdecFabric(21U)};
        for (auto &handle : handles)
        {
            if (handle.instance() == instance)
            {
                return &handle;
            }
        }
        return nullptr;
    }

    StreamFabric &streamFabric() noexcept
    {
        static StreamFabric fabric;
        return fabric;
    }

} // namespace nucode::arduino
namespace nucode::arduino::internal::stream
{
    void lockStream() noexcept
    {
        k_mutex_lock(&stream_fabric_mutex, K_FOREVER);
    }
    void unlockStream() noexcept
    {
        k_mutex_unlock(&stream_fabric_mutex);
    }
    k_spinlock &dmaMetadataLock() noexcept
    {
        return dma_metadata_lock;
    }
} // namespace nucode::arduino::internal::stream
