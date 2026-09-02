/**
 * @file main.cpp
 * @brief M15 NU54DK board/system 공개 API의 compile, link와 안전한 읽기 의미를 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <NUCODE_NU54DK.h>

#include <zephyr/ztest.h>

#include <cstddef>
#include <cstdint>
#include <string.h>

namespace
{
	using nucode::nu54dk::AlarmCallback;
	using nucode::nu54dk::BoardSystem;
	using nucode::nu54dk::Error;
	using nucode::nu54dk::PmicChargeState;
	using nucode::nu54dk::PmicRegisterWatchdog;
	using nucode::nu54dk::PmicStatus;
	using nucode::nu54dk::PmicSystemRegulation;
	using nucode::nu54dk::PmicWriteAuthorization;
	using nucode::nu54dk::ResetCause;
	using nucode::nu54dk::ResetReport;
	using nucode::nu54dk::WakeButton;

	static_assert(static_cast<std::uint32_t>(ResetCause::low_power_wake) == (1UL << 7U));
	static_assert(static_cast<std::uint8_t>(WakeButton::sw0) == 0U);
	static_assert(static_cast<std::uint8_t>(PmicChargeState::complete_or_disabled) == 3U);
	static_assert(
		static_cast<std::uint32_t>(
			PmicWriteAuthorization::acknowledge_unverified_battery_hardware) ==
		0x4E553534UL);

	/** @brief GRTC alarm callback 형식이 64-bit 예정 tick과 사용자 문맥을 유지합니다. */
	void alarmCallback(std::uint64_t scheduled_ticks, void *context)
	{
		static_cast<void>(scheduled_ticks);
		static_cast<void>(context);
	}

	/** @brief 공개 callback 별칭과 실제 함수 형식의 compile 계약입니다. */
	[[maybe_unused]] AlarmCallback callback_contract = alarmCallback;

	/**
	 * @brief 위험한 hardware 동작을 실행하지 않고 전체 API의 인자·반환 계약을 컴파일합니다.
	 *
	 * @note 이 함수는 호출하지 않으며 production source와의 최종 link는 CMake가 검증합니다.
	 */
	[[maybe_unused]] void compileFullSurface(BoardSystem &board)
	{
		char device_id[33] = {};
		ResetReport reset = {};
		std::uint8_t storage_value[8] = {};
		std::size_t actual_length = 0U;
		PmicStatus pmic_status = {};
		PmicSystemRegulation regulation = PmicSystemRegulation::battery_tracking;
		PmicRegisterWatchdog register_watchdog =
			PmicRegisterWatchdog::seconds_160_restore_register_defaults;

		static_cast<void>(board.deviceId(device_id, sizeof(device_id)));
		static_cast<void>(board.resetReport(reset));
		static_cast<void>(board.clearResetCause());
		static_cast<void>(board.watchdogBegin(1000U));
		static_cast<void>(board.watchdogFeed());
		static_cast<void>(board.watchdogStop());
		static_cast<void>(board.alarmAfterMicroseconds(1000U, alarmCallback, nullptr));
		static_cast<void>(board.cancelAlarm());
		static_cast<void>(board.storageBegin());
		static_cast<void>(board.storagePut("contract", storage_value, sizeof(storage_value)));
		static_cast<void>(board.storageGet(
			"contract", storage_value, sizeof(storage_value), actual_length));
		static_cast<void>(board.storageRemove("contract"));
		static_cast<void>(board.enterSystemOffOnButton(WakeButton::sw0));
		static_cast<void>(board.enterSystemOffAfter(1000000ULL));
		static_cast<void>(board.pmicBegin());
		static_cast<void>(board.pmicReadStatus(pmic_status));
		static_cast<void>(board.pmicReadSystemRegulation(regulation));
		static_cast<void>(board.pmicReadRegisterWatchdog(register_watchdog));
		static_cast<void>(board.pmicAuthorizeWrites(
			PmicWriteAuthorization::acknowledge_unverified_battery_hardware));
		board.pmicRevokeWrites();
		static_cast<void>(board.pmicSetChargeVoltage(4200U));
		static_cast<void>(board.pmicSetChargeCurrent(100U));
		static_cast<void>(board.pmicSetChargingEnabled(false));
		static_cast<void>(board.pmicSetRechargeThreshold(100U));
		static_cast<void>(board.pmicSetSystemRegulation(regulation));
		static_cast<void>(board.pmicSetRegisterWatchdog(register_watchdog));
		static_cast<void>(board.pmicRequestShutdown());
		static_cast<void>(board.pmicRequestShipMode());
	}
}

ZTEST(m15_board, test_identity_and_read_only_state_use_production_backend)
{
	zassert_equal(::strcmp(NU54DK.boardModel(), "NUCODE NU54DK nRF54L15 Application MCU"), 0,
				  "보드 모델 identity가 다릅니다.");
	zassert_equal(
		::strcmp(NU54DK.boardTarget(), "nrf54l15dk/nrf54l15/cpuapp/nu54dk"), 0,
		"Zephyr board target identity가 다릅니다.");
	zassert_not_null(NU54DK.socName(), "SoC identity가 nullptr입니다.");
	zassert_equal(::strcmp(NU54DK.ncsVersion(), "3.4.0"), 0,
				  "고정 NCS identity가 다릅니다.");
	zassert_not_null(NU54DK.zephyrVersion(), "Zephyr identity가 nullptr입니다.");
	zassert_not_null(NU54DK.coreVersion(), "Core identity가 nullptr입니다.");

	char device_id[33] = {};
	zassert_equal(NU54DK.deviceId(device_id, sizeof(device_id)), Error::none,
				  "device ID를 읽지 못했습니다.");
	zassert_true(device_id[0] != '\0', "device ID가 빈 문자열입니다.");

	ResetReport report = {};
	zassert_equal(NU54DK.resetReport(report), Error::none,
				  "reset cause를 읽지 못했습니다.");
	zassert_equal(report.cause & ~report.supported, 0U,
				  "지원 mask 밖 reset cause가 보고됐습니다.");

	const std::uint64_t uptime_before = NU54DK.uptimeMilliseconds();
	const std::uint64_t ticks_before = NU54DK.hardwareCounterTicks();
	k_sleep(K_MSEC(2));
	zassert_true(NU54DK.uptimeMilliseconds() >= uptime_before,
				 "64-bit uptime이 역행했습니다.");
	zassert_true(NU54DK.hardwareCounterTicks() > ticks_before,
				 "GRTC hardware counter가 진행하지 않았습니다.");
	zassert_true(NU54DK.hardwareCounterFrequency() > 0U,
				 "GRTC 주파수가 0입니다.");
	zassert_false(NU54DK.watchdogRunning(),
				  "시험이 시작하지 않은 watchdog을 실행 중으로 보고했습니다.");
	zassert_false(NU54DK.alarmPending(),
				  "시험이 예약하지 않은 alarm을 대기 중으로 보고했습니다.");
	zassert_false(NU54DK.pmicWritesAuthorized(),
				  "reset 뒤 PMIC write 승인이 자동 유지됐습니다.");
	zassert_false(NU54DK.hasBatteryTemperatureProtection(),
				  "실제 NTC가 없는 회로를 온도 보호 지원으로 보고했습니다.");
}

ZTEST_SUITE(m15_board, nullptr, nullptr, nullptr, nullptr, nullptr);
