/** @file @brief DPPI Host에서 호출하지 않는 다른 peripheral factory의 링크 의존성입니다. */
#include <nucode/EventFabric.h>
#include <cstdlib>

namespace nucode::arduino
{
    std::uint8_t TimerFabric::instance() const noexcept
    {
        std::abort();
    }
    std::uint8_t EguFabric::instance() const noexcept
    {
        std::abort();
    }
    std::uint8_t GpioteFabric::instance() const noexcept
    {
        std::abort();
    }
    std::uint8_t PpibFabric::instance() const noexcept
    {
        std::abort();
    }
} // namespace nucode::arduino
