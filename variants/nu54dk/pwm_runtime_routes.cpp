/**
 * @file pwm_runtime_routes.cpp
 * @brief NU54DK PWM runtime route의 pinctrl·PM·ownership 전환을 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "pwm_runtime_routes.h"

#include "internal/PwmRuntime.h"
#include "internal/RuntimePeripheralRoute.h"
#include "peripheral_routes.h"

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/init.h>
#include <zephyr/kernel.h>
#include <zephyr/drivers/pinctrl.h>

#include <errno.h>
#include <cstddef>
#include <cstdint>

#if defined(CONFIG_NUCODE_ARDUINO_PWM) && defined(CONFIG_PINCTRL_DYNAMIC) && \
	DT_NODE_HAS_STATUS_OKAY(DT_NODELABEL(pwm20)) &&                          \
	DT_NODE_HAS_STATUS_OKAY(DT_NODELABEL(pwm21)) &&                          \
	DT_NODE_HAS_STATUS_OKAY(DT_NODELABEL(pwm22))
#define NUCODE_NU54DK_PWM_RUNTIME_ROUTES_AVAILABLE 1

PINCTRL_DT_DEV_CONFIG_DECLARE(DT_NODELABEL(pwm20));
PINCTRL_DT_DEV_CONFIG_DECLARE(DT_NODELABEL(pwm21));
PINCTRL_DT_DEV_CONFIG_DECLARE(DT_NODELABEL(pwm22));
#else
#define NUCODE_NU54DK_PWM_RUNTIME_ROUTES_AVAILABLE 0
#endif

namespace nucode::arduino::internal
{
#if NUCODE_NU54DK_PWM_RUNTIME_ROUTES_AVAILABLE
	namespace
	{
		/** @brief production backend이 관리하는 PWM block 개수입니다. */
		constexpr std::size_t pwm_route_block_count = 3U;

		/** @brief 하나의 PWM block과 마지막 성공 route를 보존합니다. */
		struct PwmRouteState
		{
			std::uint8_t instance{0U};
			PinRoute required_route{PinRoute::none};
			const struct device *device{nullptr};
			RuntimePeripheralRoute *runtime_route{nullptr};
			PwmRuntimeRouteSet active_routes{};
			PeripheralRouteConfiguration active_configuration{};
			int last_driver_error{0};
			bool active{false};
			bool fatal{false};
		};

		RuntimePeripheralRoute pwm20_runtime_route(
			DEVICE_DT_GET(DT_NODELABEL(pwm20)),
			PINCTRL_DT_DEV_CONFIG_GET(DT_NODELABEL(pwm20)),
			{IoOwnerKind::pwm, 20U}, IoResourceKind::pwm_block, 20U);
		RuntimePeripheralRoute pwm21_runtime_route(
			DEVICE_DT_GET(DT_NODELABEL(pwm21)),
			PINCTRL_DT_DEV_CONFIG_GET(DT_NODELABEL(pwm21)),
			{IoOwnerKind::pwm, 21U}, IoResourceKind::pwm_block, 21U);
		RuntimePeripheralRoute pwm22_runtime_route(
			DEVICE_DT_GET(DT_NODELABEL(pwm22)),
			PINCTRL_DT_DEV_CONFIG_GET(DT_NODELABEL(pwm22)),
			{IoOwnerKind::pwm, 22U}, IoResourceKind::pwm_block, 22U);

		PwmRouteState pwm_route_states[pwm_route_block_count] = {
			{20U, PinRoute::pwm20, DEVICE_DT_GET(DT_NODELABEL(pwm20)), &pwm20_runtime_route, {}, {}, 0, false, false},
			{21U, PinRoute::pwm21, DEVICE_DT_GET(DT_NODELABEL(pwm21)), &pwm21_runtime_route, {}, {}, 0, false, false},
			{22U, PinRoute::pwm22, DEVICE_DT_GET(DT_NODELABEL(pwm22)), &pwm22_runtime_route, {}, {}, 0, false, false},
		};

		/** @brief instance에 대응하는 production route 상태를 반환합니다. */
		[[nodiscard]] PwmRouteState *stateForInstance(std::uint8_t instance) noexcept
		{
			for (auto &state : pwm_route_states)
			{
				if (state.instance == instance)
				{
					return &state;
				}
			}
			return nullptr;
		}

		/** @brief allocator channel 번호를 nRF PWM PSEL signal로 변환합니다. */
		[[nodiscard]] PeripheralSignal signalForChannel(std::uint8_t channel) noexcept
		{
			switch (channel)
			{
			case 0U:
				return PeripheralSignal::pwm_out0;
			case 1U:
				return PeripheralSignal::pwm_out1;
			case 2U:
				return PeripheralSignal::pwm_out2;
			case 3U:
				return PeripheralSignal::pwm_out3;
			default:
				return PeripheralSignal::invalid;
			}
		}

		/** @brief route 생성 오류를 allocator 공개 결과로 변환합니다. */
		[[nodiscard]] PwmRuntimeResult mapBuildError(
			PeripheralRouteBuildError error) noexcept
		{
			switch (error)
			{
			case PeripheralRouteBuildError::none:
				return PwmRuntimeResult::success;
			case PeripheralRouteBuildError::invalid_argument:
			case PeripheralRouteBuildError::duplicate_pin:
				return PwmRuntimeResult::invalid_argument;
			case PeripheralRouteBuildError::invalid_pin:
				return PwmRuntimeResult::invalid_pin;
			case PeripheralRouteBuildError::reserved_pin:
				return PwmRuntimeResult::ownership_conflict;
			case PeripheralRouteBuildError::device_not_ready:
				return PwmRuntimeResult::device_not_ready;
			case PeripheralRouteBuildError::unsupported_route:
			case PeripheralRouteBuildError::unsupported_capability:
			case PeripheralRouteBuildError::unsupported_gpio_port:
			default:
				return PwmRuntimeResult::unsupported_route;
			}
		}

		/** @brief route 생성 오류를 진단용 errno로 변환합니다. */
		[[nodiscard]] int buildDriverError(PeripheralRouteBuildError error) noexcept
		{
			switch (error)
			{
			case PeripheralRouteBuildError::none:
				return 0;
			case PeripheralRouteBuildError::invalid_argument:
			case PeripheralRouteBuildError::invalid_pin:
			case PeripheralRouteBuildError::duplicate_pin:
				return -EINVAL;
			case PeripheralRouteBuildError::reserved_pin:
				return -EBUSY;
			case PeripheralRouteBuildError::device_not_ready:
				return -ENODEV;
			case PeripheralRouteBuildError::unsupported_route:
			case PeripheralRouteBuildError::unsupported_capability:
			case PeripheralRouteBuildError::unsupported_gpio_port:
			default:
				return -ENOTSUP;
			}
		}

		/** @brief runtime route 오류를 allocator 공개 결과로 변환합니다. */
		[[nodiscard]] PwmRuntimeResult mapRuntimeError(
			RuntimePeripheralRouteError error) noexcept
		{
			switch (error)
			{
			case RuntimePeripheralRouteError::none:
				return PwmRuntimeResult::success;
			case RuntimePeripheralRouteError::invalid_context:
				return PwmRuntimeResult::invalid_context;
			case RuntimePeripheralRouteError::invalid_argument:
				return PwmRuntimeResult::invalid_argument;
			case RuntimePeripheralRouteError::device_not_ready:
				return PwmRuntimeResult::device_not_ready;
			case RuntimePeripheralRouteError::ownership_conflict:
			case RuntimePeripheralRouteError::pin_handover_failed:
				return PwmRuntimeResult::ownership_conflict;
			case RuntimePeripheralRouteError::not_staged:
			case RuntimePeripheralRouteError::already_active:
			case RuntimePeripheralRouteError::faulted:
			case RuntimePeripheralRouteError::pm_not_enabled:
			case RuntimePeripheralRouteError::device_not_suspended:
			case RuntimePeripheralRouteError::pinctrl_failed:
			case RuntimePeripheralRouteError::pm_failed:
			case RuntimePeripheralRouteError::release_failed:
			default:
				return PwmRuntimeResult::route_error;
			}
		}

		/** @brief 0 driver error를 포함한 route 오류에 진단값을 부여합니다. */
		[[nodiscard]] int routeDriverError(const RuntimePeripheralRoute &route) noexcept
		{
			const int driver_error = route.lastDriverError();
			return driver_error != 0 ? driver_error : -EIO;
		}

		/** @brief 복구 불가능한 route 불일치를 기록하고 해당 block 재사용을 차단합니다. */
		void latchFatal(PwmRouteState &state, int driver_error = -EIO) noexcept
		{
			state.active = state.runtime_route->active();
			state.last_driver_error = driver_error != 0 ? driver_error : -EIO;
			state.fatal = true;
		}

		/** @brief allocator route set을 검증하고 pinctrl configuration으로 생성합니다. */
		[[nodiscard]] PwmRuntimeResult buildConfiguration(
			PwmRouteState &state, const PwmRuntimeRouteSet &routes,
			PeripheralRouteConfiguration &configuration) noexcept
		{
			if ((routes.count == 0U) ||
				(routes.count > pwm_runtime_channel_capacity))
			{
				state.last_driver_error = -EINVAL;
				return PwmRuntimeResult::invalid_argument;
			}

			PeripheralSignal signals[pwm_runtime_channel_capacity]{};
			for (std::size_t index = 0U; index < routes.count; ++index)
			{
				signals[index] = signalForChannel(routes.channels[index]);
				if (signals[index] == PeripheralSignal::invalid)
				{
					state.last_driver_error = -EINVAL;
					return PwmRuntimeResult::invalid_argument;
				}
				for (std::size_t previous = 0U; previous < index; ++previous)
				{
					if (routes.channels[previous] == routes.channels[index])
					{
						state.last_driver_error = -EINVAL;
						return PwmRuntimeResult::invalid_argument;
					}
				}
			}

			const PeripheralRouteBuildError build_error = buildPeripheralRoute(
				state.required_route, routes.pins, signals, routes.count, configuration);
			state.last_driver_error = buildDriverError(build_error);
			return mapBuildError(build_error);
		}

		/** @brief 새 route 적용 실패 후 이전 활성 route를 복원합니다. */
		[[nodiscard]] bool restorePreviousRoute(
			PwmRouteState &state,
			const PeripheralRouteConfiguration &previous_configuration,
			const PwmRuntimeRouteSet &previous_routes) noexcept
		{
			if (!state.runtime_route->stage(previous_configuration) ||
				!state.runtime_route->activate())
			{
				latchFatal(state, routeDriverError(*state.runtime_route));
				return false;
			}

			state.active_configuration = previous_configuration;
			state.active_routes = previous_routes;
			state.active = true;
			return true;
		}

		/** @brief 지정 핀이 production PWM route에 배치될 수 있는지 검증합니다. */
		[[nodiscard]] bool supportsRoute(pin_size_t pin,
										 std::uint8_t block_instance) noexcept
		{
			PwmRouteState *const state = stateForInstance(block_instance);
			if (state == nullptr || state->fatal || state->device == nullptr ||
				!device_is_ready(state->device))
			{
				return false;
			}

			const PwmRuntimeRouteSet route{{pin}, {0U}, 1U};
			PeripheralRouteConfiguration configuration{};
			return buildConfiguration(*state, route, configuration) ==
				   PwmRuntimeResult::success;
		}

		/** @brief allocator에 PWM block 장치와 polarity를 제공합니다. */
		[[nodiscard]] PwmRuntimeResult resolveBlock(
			std::uint8_t block_instance, PwmRuntimeBlock &block) noexcept
		{
			block = {};
			PwmRouteState *const state = stateForInstance(block_instance);
			if (state == nullptr)
			{
				return PwmRuntimeResult::invalid_argument;
			}
			if (state->fatal)
			{
				state->last_driver_error = -EIO;
				return PwmRuntimeResult::route_error;
			}
			if (state->device == nullptr || !device_is_ready(state->device))
			{
				state->last_driver_error = -ENODEV;
				return PwmRuntimeResult::device_not_ready;
			}

			block.device = state->device;
			block.flags = 0U;
			state->last_driver_error = 0;
			return PwmRuntimeResult::success;
		}

		/** @brief PWM block의 전체 desired route를 원자적으로 교체합니다. */
		[[nodiscard]] PwmRuntimeResult applyRoutes(
			std::uint8_t block_instance, const PwmRuntimeRouteSet &routes) noexcept
		{
			if (k_is_in_isr())
			{
				return PwmRuntimeResult::invalid_context;
			}
			PwmRouteState *const state = stateForInstance(block_instance);
			if (state == nullptr)
			{
				return PwmRuntimeResult::invalid_argument;
			}
			if (state->fatal)
			{
				state->last_driver_error = -EIO;
				return PwmRuntimeResult::route_error;
			}

			PeripheralRouteConfiguration next_configuration{};
			const PwmRuntimeResult build_result =
				buildConfiguration(*state, routes, next_configuration);
			if (build_result != PwmRuntimeResult::success)
			{
				return build_result;
			}

			if (state->active != state->runtime_route->active())
			{
				latchFatal(*state);
				return PwmRuntimeResult::route_error;
			}

			const bool had_previous = state->active;
			const PeripheralRouteConfiguration previous_configuration =
				state->active_configuration;
			const PwmRuntimeRouteSet previous_routes = state->active_routes;

			if (had_previous && !state->runtime_route->deactivate())
			{
				state->active = state->runtime_route->active();
				state->last_driver_error = routeDriverError(*state->runtime_route);
				if (state->runtime_route->faulted() || !state->active)
				{
					latchFatal(*state, state->last_driver_error);
					return PwmRuntimeResult::route_error;
				}
				return mapRuntimeError(state->runtime_route->lastError());
			}

			if (!state->runtime_route->stage(next_configuration))
			{
				const PwmRuntimeResult original_result =
					mapRuntimeError(state->runtime_route->lastError());
				const int original_driver_error =
					routeDriverError(*state->runtime_route);
				if (had_previous && !restorePreviousRoute(
										*state, previous_configuration, previous_routes))
				{
					return PwmRuntimeResult::route_error;
				}
				if (!had_previous && state->runtime_route->faulted())
				{
					latchFatal(*state, original_driver_error);
					return PwmRuntimeResult::route_error;
				}
				state->active = had_previous;
				state->last_driver_error = original_driver_error;
				return original_result;
			}

			if (!state->runtime_route->activate())
			{
				const PwmRuntimeResult original_result =
					mapRuntimeError(state->runtime_route->lastError());
				const int original_driver_error =
					routeDriverError(*state->runtime_route);
				if (had_previous && !restorePreviousRoute(
										*state, previous_configuration, previous_routes))
				{
					return PwmRuntimeResult::route_error;
				}
				if (!had_previous && state->runtime_route->faulted())
				{
					latchFatal(*state, original_driver_error);
					return PwmRuntimeResult::route_error;
				}
				state->active = had_previous;
				state->last_driver_error = original_driver_error;
				return original_result;
			}

			state->active_configuration = next_configuration;
			state->active_routes = routes;
			state->last_driver_error = 0;
			state->active = true;
			return PwmRuntimeResult::success;
		}

		/** @brief PWM block의 활성 route를 제거하고 이전 GPIO 상태를 복원합니다. */
		[[nodiscard]] PwmRuntimeResult clearRoutes(std::uint8_t block_instance) noexcept
		{
			if (k_is_in_isr())
			{
				return PwmRuntimeResult::invalid_context;
			}
			PwmRouteState *const state = stateForInstance(block_instance);
			if (state == nullptr)
			{
				return PwmRuntimeResult::invalid_argument;
			}
			if (state->fatal)
			{
				state->last_driver_error = -EIO;
				return PwmRuntimeResult::route_error;
			}
			if (state->active != state->runtime_route->active())
			{
				latchFatal(*state);
				return PwmRuntimeResult::route_error;
			}

			if (!state->active)
			{
				state->active_routes = {};
				state->active_configuration = {};
				state->last_driver_error = 0;
				state->active = false;
				return PwmRuntimeResult::success;
			}
			if (!state->runtime_route->deactivate())
			{
				state->active = state->runtime_route->active();
				state->last_driver_error = routeDriverError(*state->runtime_route);
				if (state->runtime_route->faulted() || !state->active)
				{
					latchFatal(*state, state->last_driver_error);
					return PwmRuntimeResult::route_error;
				}
				return mapRuntimeError(state->runtime_route->lastError());
			}

			state->active_routes = {};
			state->active_configuration = {};
			state->last_driver_error = 0;
			state->active = false;
			return PwmRuntimeResult::success;
		}

		/** @brief 지정 block의 마지막 production route 진단값을 반환합니다. */
		[[nodiscard]] int lastDriverError(std::uint8_t block_instance) noexcept
		{
			const PwmRouteState *const state = stateForInstance(block_instance);
			return state != nullptr ? state->last_driver_error : -EINVAL;
		}

		const PwmRuntimeRouteBackend production_backend{
			supportsRoute,
			resolveBlock,
			applyRoutes,
			clearRoutes,
			lastDriverError,
		};
	}
#endif

	bool installNu54dkPwmRuntimeRouteBackend() noexcept
	{
#if NUCODE_NU54DK_PWM_RUNTIME_ROUTES_AVAILABLE
		return installPwmRuntimeRouteBackend(production_backend);
#else
		return false;
#endif
	}
}

#if defined(CONFIG_NUCODE_ARDUINO_PWM)
namespace
{
	/** @brief Arduino application init 단계에 production PWM backend를 자동 설치합니다. */
	int initializeNu54dkPwmRuntimeRoutes()
	{
		static_cast<void>(
			nucode::arduino::internal::installNu54dkPwmRuntimeRouteBackend());
		return 0;
	}
}

SYS_INIT(initializeNu54dkPwmRuntimeRoutes, APPLICATION,
		 CONFIG_APPLICATION_INIT_PRIORITY);
#endif
