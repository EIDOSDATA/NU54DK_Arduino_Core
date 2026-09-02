/**
 * @file io_resource_registry.cpp
 * @brief NU54DK Devicetree pinctrl에서 부팅 고정 자원 소유권을 생성합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "internal/Nu54dkIoResources.h"

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/dt-bindings/pinctrl/nrf-pinctrl.h>
#include <zephyr/init.h>
#include <zephyr/kernel.h>

#include <errno.h>
#include <cstddef>
#include <cstdint>

namespace nucode::arduino::internal
{
	namespace
	{
		IoResourceLease uart20_lease{};
		IoResourceResult registry_result = IoResourceResult::success;
#if !defined(CONFIG_ZTEST)
		bool registry_initialized = false;
#endif

		/** @brief nRF PSEL 값에서 port를 포함한 연속 pin 번호를 추출합니다. */
		[[nodiscard]] constexpr std::uint16_t pselPin(std::uint32_t psel) noexcept
		{
			return static_cast<std::uint16_t>((psel >> NRF_PIN_POS) & NRF_PIN_MSK);
		}

		/** @brief 연속 pin 번호에 맞는 Zephyr GPIO controller를 반환합니다. */
		[[nodiscard]] const struct device *gpioController(std::uint16_t absolute_pin) noexcept
		{
			switch (absolute_pin / 32U)
			{
			case 0U:
				return DEVICE_DT_GET(DT_NODELABEL(gpio0));
			case 1U:
				return DEVICE_DT_GET(DT_NODELABEL(gpio1));
			case 2U:
				return DEVICE_DT_GET(DT_NODELABEL(gpio2));
			default:
				return nullptr;
			}
		}

		/** @brief nRF PSEL 값을 정규화된 GPIO pad 자원으로 변환합니다. */
		[[nodiscard]] IoResourceId pselResource(std::uint32_t psel) noexcept
		{
			const std::uint16_t absolute_pin = pselPin(psel);
			return {IoResourceKind::gpio_pin, gpioController(absolute_pin),
					static_cast<std::uint16_t>(absolute_pin % 32U)};
		}

		/** @brief 하나의 고정 owner batch를 reserve 후 즉시 commit합니다. */
		[[nodiscard]] IoResourceResult registerFixedResources(
			IoResourceOwner owner, const IoResourceId *resources, std::size_t count,
			IoResourceLease &lease) noexcept
		{
			lease = {};
			const IoResourceResult reserve_result = reserveIoResources(
				owner, resources, count, IoAcquirePolicy::exclusive, lease);
			if (reserve_result != IoResourceResult::success)
			{
				return reserve_result;
			}
			return commitIoResources(lease);
		}

		/** @brief 부분 등록된 lease를 이전 free 상태로 되돌립니다. */
		void unwindFixedLease(IoResourceLease &lease,
							  IoResourceResult &first_error) noexcept
		{
			IoResourceResult result = IoResourceResult::success;
			if (lease.phase == IoLeasePhase::reserved)
			{
				result = rollbackIoResources(lease);
			}
			else if (lease.phase == IoLeasePhase::committed)
			{
				result = releaseIoResources(lease);
			}

			if (result == IoResourceResult::success)
			{
				lease = {};
			}
			else if (first_error == IoResourceResult::success)
			{
				first_error = result;
			}
		}

		/** @brief 부팅 고정 UART20 등록 transaction을 해제합니다. */
		[[nodiscard]] IoResourceResult unwindRegisteredResources() noexcept
		{
			IoResourceResult first_error = IoResourceResult::success;
			unwindFixedLease(uart20_lease, first_error);
			return first_error;
		}

		/** @brief 등록 실패 원인과 rollback 실패를 하나의 fail-closed 결과로 합칩니다. */
		[[nodiscard]] IoResourceResult failRegistryInitialization(
			IoResourceResult cause) noexcept
		{
			const IoResourceResult unwind_result = unwindRegisteredResources();
			return unwind_result == IoResourceResult::success ? cause : unwind_result;
		}

		/** @brief APPLICATION init 단계에서 C++ 정적 초기화 후 registry를 채웁니다. */
		int initializeRegistryAtBoot()
		{
			registry_result = initializeNu54dkIoResources();
			if (registry_result != IoResourceResult::success)
			{
				k_panic();
				return -EBUSY;
			}
			return 0;
		}
	}

	IoResourceResult initializeNu54dkIoResources() noexcept
	{
#if defined(CONFIG_ZTEST)
		uart20_lease = {};
#else
		if (registry_initialized)
		{
			return registry_result;
		}
		registry_initialized = true;
#endif

		const IoResourceId uart20_resources[] = {
			pselResource(DT_PROP_BY_IDX(DT_CHILD(DT_NODELABEL(uart20_default), group1),
										psels, 0)),
			pselResource(DT_PROP_BY_IDX(DT_CHILD(DT_NODELABEL(uart20_default), group1),
										psels, 1)),
			pselResource(DT_PROP_BY_IDX(DT_CHILD(DT_NODELABEL(uart20_default), group2),
										psels, 0)),
			pselResource(DT_PROP_BY_IDX(DT_CHILD(DT_NODELABEL(uart20_default), group2),
										psels, 1)),
			peripheralIoResource(IoResourceKind::serial_block, 20U),
		};
		IoResourceResult result = registerFixedResources(
			{IoOwnerKind::serial, 20U}, uart20_resources,
			sizeof(uart20_resources) / sizeof(uart20_resources[0]), uart20_lease);
		if (result != IoResourceResult::success)
		{
			return failRegistryInitialization(result);
		}

		/**
		 * Wire22, PWM20/21/22와 SPI00은 Arduino begin()/end() 수명주기에서
		 * route와 block을 동적으로 획득합니다. 부팅 시 pad를 고정하면 GPIO에서
		 * 주변장치로 넘기는 2단계 handover가 시작되기 전에 충돌하므로 등록하지
		 * 않습니다. 콘솔 UART20만 실제 부팅 고정 소유자로 유지합니다.
		 */
		return result;
	}

	IoResourceResult nu54dkIoResourceRegistryResult() noexcept
	{
		return registry_result;
	}

	SYS_INIT(initializeRegistryAtBoot, APPLICATION, CONFIG_APPLICATION_INIT_PRIORITY);
}
