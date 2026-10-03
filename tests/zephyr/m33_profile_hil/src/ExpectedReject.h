/** @file @brief 한 요청의 GAP·상세 ATT 오류를 순서와 무관하게 한 번씩 결합합니다.
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include <stdint.h>

/** @brief token의 link generation과 단계를 고정하고 두 callback 사이를 100ms로 제한합니다. */
template <typename Handle> class ExpectedReject
{
  public:
    bool begin(Handle handle, unsigned index, unsigned phase, int driver, unsigned att)
    {
        if (active_)
        {
            return false;
        }
        handle_ = handle;
        index_ = index;
        phase_ = phase;
        driver_ = driver;
        att_ = att;
        gap_ = false;
        detail_ = false;
        active_ = true;
        return true;
    }
    bool active() const
    {
        return active_;
    }
    bool matched() const
    {
        return active_ && gap_ && detail_;
    }
    bool expired(uint32_t now) const
    {
        return active_ && (gap_ || detail_) && now - first_at_ > 100U;
    }
    bool gap(Handle handle, unsigned index, unsigned phase, int driver, unsigned att, uint32_t now)
    {
        return accept(true, handle, index, phase, driver, att, now);
    }
    bool detail(Handle handle, unsigned index, unsigned phase, int status, unsigned att,
                uint32_t now)
    {
        if (status != (att_ != 0U ? -static_cast<int>(att_) : driver_))
        {
            return false;
        }
        return accept(false, handle, index, phase, driver_, att, now);
    }
    bool finish()
    {
        if (!matched())
        {
            return false;
        }
        active_ = false;
        return true;
    }
    /** @brief 정상 write ACK는 오류 callback을 하나도 소비하지 않은 token만 닫습니다. */
    bool acknowledge()
    {
        if (!active_ || gap_ || detail_)
        {
            return false;
        }
        active_ = false;
        return true;
    }

  private:
    bool accept(bool gap, Handle handle, unsigned index, unsigned phase, int driver, unsigned att,
                uint32_t now)
    {
        if (!active_ || handle != handle_ || index != index_ || phase != phase_ ||
            driver != driver_ || att != att_ || expired(now) || (gap ? gap_ : detail_))
        {
            return false;
        }
        if (!gap_ && !detail_)
        {
            first_at_ = now;
        }
        if (gap)
        {
            gap_ = true;
        }
        else
        {
            detail_ = true;
        }
        return true;
    }
    Handle handle_{};
    unsigned index_ = 0U, phase_ = 0U, att_ = 0U;
    int driver_ = 0;
    uint32_t first_at_ = 0U;
    bool active_ = false, gap_ = false, detail_ = false;
};
