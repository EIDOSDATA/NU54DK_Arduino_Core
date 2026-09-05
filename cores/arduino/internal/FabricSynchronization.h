/**
 * @file FabricSynchronization.h
 * @brief Fabric의 ISR 진단 snapshot과 현재 실행의 정지 신호를 보호합니다.
 * SPDX-License-Identifier: MIT
 */
#ifndef NUCODE_INTERNAL_FABRIC_SYNCHRONIZATION_H_
#define NUCODE_INTERNAL_FABRIC_SYNCHRONIZATION_H_
#include <zephyr/kernel.h>
#include <cstdint>

namespace nucode::arduino::internal
{
    /** @brief 결과와 native 오류를 한 번의 spinlock 경계에서 읽고 씁니다. */
    template <typename Result> class FabricDiagnostic
    {
      public:
        struct Snapshot
        {
            Result result{Result::success};
            int driver_error{0};
        };
        void record(Result result, int driver_error) noexcept
        {
            const auto key = k_spin_lock(&lock_);
            value_ = {result, driver_error};
            k_spin_unlock(&lock_, key);
        }
        [[nodiscard]] Snapshot snapshot() const noexcept
        {
            const auto key = k_spin_lock(&lock_);
            const auto value = value_;
            k_spin_unlock(&lock_, key);
            return value;
        }

      private:
        mutable k_spinlock lock_{};
        Snapshot value_{};
    };

    /**
     * @brief 정지 요청 이전 신호와 이전 실행의 waiter를 구분합니다.
     * @details 새 실행 전 hardware/IRQ의 정지 경계가 필요합니다. timeout 뒤 같은 실행의
     * 신호를 유지하며, ISR 알림은 queue가 가득 차도 전달됩니다. hardware request ID를 만들지는 않습니다.
     */
    class FabricStopSignal
    {
      public:
        void beginRun() noexcept
        {
            const auto key = k_spin_lock(&lock_);
            ++generation_;
            armed_ = false;
            stopped_ = false;
            k_spin_unlock(&lock_, key);
        }
        [[nodiscard]] std::uint32_t arm() noexcept
        {
            const auto key = k_spin_lock(&lock_);
            if (!armed_)
            {
                armed_ = true;
                stopped_ = false;
            }
            const auto generation = generation_;
            k_spin_unlock(&lock_, key);
            return generation;
        }
        void notifyStopped() noexcept
        {
            const auto key = k_spin_lock(&lock_);
            if (armed_)
            {
                stopped_ = true;
            }
            k_spin_unlock(&lock_, key);
        }
        [[nodiscard]] bool completed(std::uint32_t generation) const noexcept
        {
            const auto key = k_spin_lock(&lock_);
            const bool complete = armed_ && stopped_ && generation_ == generation;
            k_spin_unlock(&lock_, key);
            return complete;
        }

      private:
        mutable k_spinlock lock_{};
        std::uint32_t generation_{0U};
        bool armed_{false};
        bool stopped_{false};
    };

    /** @brief 호출자가 mutex를 놓은 상태에서 마지막 us까지 overflow 없이 정지를 기다립니다. */
    template <typename Predicate>
    [[nodiscard]] bool waitFabricStop(Predicate stopped, std::uint32_t remaining_us) noexcept
    {
        while (!stopped() && remaining_us != 0U)
        {
            const auto interval = remaining_us < 10U ? remaining_us : 10U;
            k_busy_wait(interval);
            remaining_us -= interval;
        }
        return stopped();
    }
} // namespace nucode::arduino::internal
#endif
