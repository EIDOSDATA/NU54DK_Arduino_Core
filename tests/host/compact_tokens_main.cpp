/** @file @brief compact token과 기존 lease 경로의 충돌·세대·원자성을 독립 비교합니다. */
#include "internal/resource/IoResourceTable.h"
#include <cassert>
#include <cstdint>
using namespace nucode::arduino::internal;
using io_resource_detail::IoResourceTable;

/** @brief 수정 전 reserve/commit 변환을 비교 기준으로 실행합니다. */
IoResourceResult slowAcquire(IoResourceTable &table, IoResourceOwner owner,
                             const IoResourceId *resources, std::size_t count,
                             IoResourceToken &token)
{
    if (count == 0U || count > io_resource_token_capacity || token.active)
    {
        return IoResourceResult::invalid_argument;
    }
    IoResourceLease lease{};
    auto result = table.reserveIoResources(owner, resources, count, IoAcquirePolicy::exclusive,
                                           lease, nullptr);
    if (result != IoResourceResult::success)
    {
        return result;
    }
    result = table.commitIoResources(lease);
    assert(result == IoResourceResult::success);
    token = {};
    token.owner = lease.owner;
    token.manager_epoch = lease.manager_epoch;
    token.count = lease.count;
    for (std::size_t index = 0U; index < count; ++index)
    {
        token.entries[index] = {lease.entries[index].resource, lease.entries[index].generation,
                                lease.entries[index].changed};
    }
    token.active = true;
    return result;
}

/** @brief 수정 전 token→lease 반환에서 stale·차용·부분 반환 거부를 보존합니다. */
IoResourceResult slowRelease(IoResourceTable &table, IoResourceToken &token)
{
    if (!token.active || token.count == 0U || token.count > io_resource_token_capacity)
    {
        return IoResourceResult::wrong_phase;
    }
    IoResourceLease lease{};
    lease.owner = token.owner;
    lease.phase = IoLeasePhase::committed;
    lease.manager_epoch = token.manager_epoch;
    lease.count = token.count;
    for (std::size_t index = 0U; index < token.count; ++index)
    {
        lease.entries[index].resource = token.entries[index].resource;
        lease.entries[index].generation = token.entries[index].generation;
        lease.entries[index].changed = token.entries[index].changed;
    }
    const auto result = table.releaseIoResources(lease);
    if (result == IoResourceResult::success)
    {
        token = {};
    }
    return result;
}

int main()
{
    IoResourceTable compact, baseline;
    IoResourceToken actual[12]{}, expected[12]{};
    std::uint32_t random = 0x13579bdfU;
    for (unsigned step = 0U; step < 4000U; ++step)
    {
        random = random * 1664525U + 1013904223U;
        const unsigned index = (random >> 16U) % 12U;
        const IoResourceOwner owner{IoOwnerKind::i2s, static_cast<std::uint8_t>(random % 2U)};
        const auto address = 0x20000000U + ((random >> 8U) % 12U) * 32U;
        const IoResourceId resources[]{
            dmaMemoryIoResource(reinterpret_cast<void *>(address), 64U),
            dmaMemoryIoResource(reinterpret_cast<void *>(address + 32U * ((random >> 4U) % 5U)),
                                32U)};
        const auto count = 1U + ((random >> 3U) % 2U);
        if (step % 97U == 0U)
        {
            compact.resetIoResourceManagerForTest();
            baseline.resetIoResourceManagerForTest();
            for (unsigned slot = 0U; slot < 12U; ++slot)
            {
                if (actual[slot].active)
                {
                    assert(compact.releaseIoResources(actual[slot]) ==
                           IoResourceResult::stale_lease);
                    assert(slowRelease(baseline, expected[slot]) == IoResourceResult::stale_lease);
                }
                actual[slot] = {};
                expected[slot] = {};
            }
        }
        else if (step % 11U == 0U)
        {
            auto bad_actual = actual[index], bad_expected = expected[index];
            ++bad_actual.entries[0].generation;
            ++bad_expected.entries[0].generation;
            assert(compact.releaseIoResources(bad_actual) == slowRelease(baseline, bad_expected));
        }
        else if ((random & 4U) != 0U)
        {
            assert(compact.acquireIoResources(owner, resources, count, IoAcquirePolicy::exclusive,
                                              actual[index], nullptr) ==
                   slowAcquire(baseline, owner, resources, count, expected[index]));
        }
        else
        {
            assert(compact.releaseIoResources(actual[index]) ==
                   slowRelease(baseline, expected[index]));
        }
        for (unsigned probe = 0U; probe < 18U; ++probe)
        {
            const auto resource =
                dmaMemoryIoResource(reinterpret_cast<void *>(0x20000000U + probe * 32U), 32U);
            IoResourceSnapshot left{}, right{};
            assert(compact.ioResourceSnapshot(resource, left) ==
                   baseline.ioResourceSnapshot(resource, right));
            assert(left.owner.kind == right.owner.kind &&
                   left.owner.instance == right.owner.instance && left.state == right.state &&
                   left.generation == right.generation);
        }
        for (unsigned slot = 0U; slot < 12U; ++slot)
        {
            assert(actual[slot].active == expected[slot].active &&
                   actual[slot].count == expected[slot].count &&
                   actual[slot].manager_epoch == expected[slot].manager_epoch);
            for (std::size_t entry = 0U; entry < actual[slot].count; ++entry)
            {
                assert(actual[slot].entries[entry].generation ==
                           expected[slot].entries[entry].generation &&
                       actual[slot].entries[entry].changed ==
                           expected[slot].entries[entry].changed);
            }
        }
    }
    compact.resetIoResourceManagerForTest();
    IoResourceToken held{}, borrower{};
    const IoResourceOwner owner{IoOwnerKind::i2s, 20U};
    const auto resource = dmaMemoryIoResource(reinterpret_cast<void *>(0x20000000U), 128U);
    assert(compact.acquireIoResources(owner, &resource, 1U, IoAcquirePolicy::exclusive, held,
                                      nullptr) == IoResourceResult::success);
    IoResourceLease reservation{};
    assert(compact.reserveIoResources(owner, &resource, 1U, IoAcquirePolicy::exclusive, reservation,
                                      nullptr) == IoResourceResult::success);
    assert(compact.releaseIoResources(held) == IoResourceResult::conflict);
    assert(compact.acquireIoResources(owner, &resource, 1U, IoAcquirePolicy::exclusive, borrower,
                                      nullptr) == IoResourceResult::conflict);
    assert(compact.rollbackIoResources(reservation) == IoResourceResult::success);
    assert(compact.acquireIoResources(owner, &resource, 1U, IoAcquirePolicy::exclusive, borrower,
                                      nullptr) == IoResourceResult::success);
    assert(!borrower.entries[0].changed);
    assert(compact.releaseIoResources(borrower) == IoResourceResult::success);
    assert(compact.releaseIoResources(held) == IoResourceResult::success);
}
