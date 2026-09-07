/** @file @brief 시험이 예약한 자원에서 public API의 원자적 충돌 거부를 확인합니다. */
#pragma once

namespace
{
    /** @brief 실제 system 자원을 빼앗지 않고 빈 자원에 시험용 system 예약을 만듭니다. */
    template <typename Acquire>
    bool refusesReservation(const IoResourceId &resource, Acquire acquire)
    {
        IoResourceLease lease{};
        if (reserveIoResources({IoOwnerKind::system, 0xFFU}, &resource, 1U,
                               IoAcquirePolicy::exclusive, lease) != IoResourceResult::success)
        {
            return false;
        }
        const auto result = acquire();
        IoResourceSnapshot snapshot{};
        const bool unchanged =
            ioResourceSnapshot(resource, snapshot) == IoResourceResult::success &&
            snapshot.state == IoResourceState::reserved &&
            snapshot.owner.kind == IoOwnerKind::system && snapshot.owner.instance == 0xFFU;
        const auto rollback = rollbackIoResources(lease);
        return result == EventFabricResult::ownership_conflict && unchanged &&
               rollback == IoResourceResult::success && resourceFree(resource);
    }
} // namespace
