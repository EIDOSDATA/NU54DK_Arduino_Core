/**
 * @file main.cpp
 * @brief M15 비버튼 board/system 기능을 UART 상태 머신으로 자동 검증합니다.
 *
 * @note 이 image는 버튼 wake와 BQ25186 쓰기 API를 호출하지 않습니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <NUCODE_NU54DK.h>

#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/reboot.h>

#include <cstddef>
#include <cstdint>
#include <ctype.h>
#include <string.h>

namespace
{
	using nucode::nu54dk::Error;
	using nucode::nu54dk::ResetCause;
	using nucode::nu54dk::ResetReport;

	/** @brief UART protocol schema입니다. */
	constexpr std::uint32_t protocol_schema = 1U;

	/** @brief 저장 상태의 손상·다른 image 오인을 막는 magic입니다. */
	constexpr std::uint32_t state_magic = 0x4D313541UL;

	/** @brief 호스트가 보내는 nonce의 고정 16진 문자 수입니다. */
	constexpr std::size_t nonce_length = 32U;

	/** @brief GRTC alarm의 상대 지연입니다. */
	constexpr std::uint64_t alarm_delay_us = 200000ULL;

	/** @brief timed System OFF wake의 상대 지연입니다. */
	constexpr std::uint64_t system_off_delay_us = 2000000ULL;

	/** @brief watchdog stop 생존 시험의 timeout입니다. */
	constexpr std::uint32_t watchdog_stop_timeout_ms = 2000U;

	/** @brief 실제 watchdog reset 시험의 timeout입니다. */
	constexpr std::uint32_t watchdog_expiry_timeout_ms = 1500U;

	/** @brief Settings/ZMS에 저장할 상태 key입니다. */
	constexpr char state_key[] = "m15.auto.state";

	/** @brief Settings/ZMS save/load/delete 의미 시험 key입니다. */
	constexpr char payload_key[] = "m15.auto.data";

	/** @brief save/load/delete 시험에 사용하는 고정 payload입니다. */
	constexpr std::uint8_t expected_payload[] = {
		0x4EU, 0x55U, 0x43U, 0x4FU, 0x44U, 0x45U, 0x15U, 0xA5U,
	};

	/** @brief 재부팅 경계에서 이어 갈 자동 HIL 단계입니다. */
	enum class Stage : std::uint32_t
	{
		idle = 0U,
		soft_reset = 1U,
		watchdog_arm = 2U,
		watchdog_wait = 3U,
		timed_wake_wait = 4U,
	};

	/** @brief Settings/ZMS에 저장하는 고정 크기 상태 record입니다. */
	struct ScenarioState
	{
		std::uint32_t magic = state_magic;
		std::uint32_t schema = protocol_schema;
		Stage stage = Stage::idle;
		char nonce[nonce_length + 1U] = {};
		std::uint32_t guard = 0U;
	};

	/** @brief GRTC callback 횟수를 ISR-safe atomic으로 보관합니다. */
	atomic_t alarm_callback_count = ATOMIC_INIT(0);

	/** @brief GRTC callback이 전달한 예정 tick입니다. */
	std::uint64_t alarm_scheduled_ticks = 0U;

	/** @brief alarm callback 완료를 setup thread에 전달합니다. */
	K_SEM_DEFINE(alarm_completed, 0, 1);

	/** @brief 부팅 직후 읽은 reset 원인입니다. */
	ResetReport boot_reset_report = {};

	/** @brief ScenarioState guard를 계산합니다. */
	std::uint32_t stateGuard(const ScenarioState &state)
	{
		std::uint32_t guard = state.magic ^ state.schema ^
			static_cast<std::uint32_t>(state.stage) ^ 0xA55A15A5UL;
		for (std::size_t index = 0U; index < nonce_length; ++index)
		{
			guard = (guard << 5U) | (guard >> 27U);
			guard ^= static_cast<std::uint8_t>(state.nonce[index]);
		}
		return guard;
	}

	/** @brief protocol에 사용할 단계 이름을 반환합니다. */
	const char *stageName(Stage stage)
	{
		switch (stage)
		{
		case Stage::idle:
			return "idle";
		case Stage::soft_reset:
			return "soft_reset";
		case Stage::watchdog_arm:
			return "watchdog_arm";
		case Stage::watchdog_wait:
			return "watchdog_wait";
		case Stage::timed_wake_wait:
			return "timed_wake_wait";
		default:
			return "invalid";
		}
	}

	/** @brief 공개 오류와 driver 오류를 기록하고 안전하게 멈춥니다. */
	[[noreturn]] void fail(const char *stage, Error error = Error::driver_error)
	{
		Serial.print("NUCODE_M15_AUTO_FAIL:stage=");
		Serial.print(stage);
		Serial.print(":error=");
		Serial.print(static_cast<unsigned int>(error));
		Serial.print(":driver_error=");
		Serial.println(NU54DK.lastDriverError());
		Serial.flush();
		for (;;)
		{
			k_sleep(K_SECONDS(1));
		}
	}

	/** @brief API 결과가 성공이 아니면 fail-closed로 중단합니다. */
	void requireSuccess(Error result, const char *stage)
	{
		if (result != Error::none)
		{
			fail(stage, result);
		}
	}

	/** @brief reset cause에 기대 bit가 포함됐는지 확인합니다. */
	void requireResetCause(ResetCause expected, const char *phase)
	{
		const auto mask = static_cast<std::uint32_t>(expected);
		if ((boot_reset_report.cause & mask) == 0U)
		{
			fail(phase, Error::driver_error);
		}
		Serial.print("NUCODE_M15_AUTO_RESET:PASS:phase=");
		Serial.print(phase);
		Serial.print(":cause=");
		Serial.print(static_cast<unsigned long>(boot_reset_report.cause));
		Serial.print(":supported=");
		Serial.println(static_cast<unsigned long>(boot_reset_report.supported));
	}

	/** @brief 고정 길이 소문자 16진 nonce인지 검사합니다. */
	bool validNonce(const char *nonce)
	{
		if ((nonce == nullptr) || (::strlen(nonce) != nonce_length))
		{
			return false;
		}
		for (std::size_t index = 0U; index < nonce_length; ++index)
		{
			const unsigned char character = static_cast<unsigned char>(nonce[index]);
			if ((::isdigit(character) == 0) &&
				((character < 'a') || (character > 'f')))
			{
				return false;
			}
		}
		return true;
	}

	/** @brief 지정 길이의 소문자 16진 문자열인지 검사합니다. */
	bool validHexadecimal(const char *value, std::size_t length)
	{
		if ((value == nullptr) || (::strlen(value) != length))
		{
			return false;
		}
		for (std::size_t index = 0U; index < length; ++index)
		{
			const unsigned char character = static_cast<unsigned char>(value[index]);
			if ((::isdigit(character) == 0) &&
				((character < 'a') || (character > 'f')))
			{
				return false;
			}
		}
		return true;
	}

	/** @brief 상태 record 자체와 nonce guard를 검사합니다. */
	bool validState(const ScenarioState &state)
	{
		const auto raw_stage = static_cast<std::uint32_t>(state.stage);
		return (state.magic == state_magic) && (state.schema == protocol_schema) &&
			(raw_stage >= static_cast<std::uint32_t>(Stage::soft_reset)) &&
			(raw_stage <= static_cast<std::uint32_t>(Stage::timed_wake_wait)) &&
			validNonce(state.nonce) && (state.guard == stateGuard(state));
	}

	/** @brief 다음 단계를 원자적 settings value 하나로 저장합니다. */
	void saveState(ScenarioState &state, Stage next_stage)
	{
		state.stage = next_stage;
		state.guard = stateGuard(state);
		requireSuccess(NU54DK.storagePut(state_key, &state, sizeof(state)), "STATE_SAVE");
	}

	/** @brief 현재 HIL state와 nonce를 UART로 알립니다. */
	void reportState(const ScenarioState *state, const char *name)
	{
		Serial.print("NUCODE_M15_AUTO_STATE:schema=1:stage=");
		Serial.print(name);
		Serial.print(":nonce=");
		Serial.println(state == nullptr ? "none" : state->nonce);
		Serial.flush();
	}

	/** @brief CR/LF 한 줄을 정해진 buffer 범위 안에서 blocking 수신합니다. */
	bool readCommand(char *destination, std::size_t capacity)
	{
		if ((destination == nullptr) || (capacity < 2U))
		{
			return false;
		}
		std::size_t length = 0U;
		for (;;)
		{
			if (Serial.available() <= 0)
			{
				k_sleep(K_MSEC(5));
				continue;
			}
			const int value = Serial.read();
			if (value < 0)
			{
				continue;
			}
			if (value == '\r')
			{
				continue;
			}
			if (value == '\n')
			{
				destination[length] = '\0';
				return length > 0U;
			}
			if (length + 1U >= capacity)
			{
				return false;
			}
			destination[length++] = static_cast<char>(value);
		}
	}

	/** @brief GRTC callback에서 예정 tick을 보존하고 semaphore를 신호합니다. */
	void alarmCallback(std::uint64_t scheduled_ticks, void *context)
	{
		ARG_UNUSED(context);
		alarm_scheduled_ticks = scheduled_ticks;
		atomic_inc(&alarm_callback_count);
		k_sem_give(&alarm_completed);
	}

	/** @brief identity, device ID, reset report와 64-bit uptime을 검증합니다. */
	void testIdentityAndTime(void)
	{
		char device_id[33] = {};
		requireSuccess(NU54DK.deviceId(device_id, sizeof(device_id)), "DEVICE_ID");
		const std::size_t identifier_length = ::strlen(device_id);
		if (((identifier_length != 16U) && (identifier_length != nonce_length)) ||
			!validHexadecimal(device_id, identifier_length))
		{
			fail("DEVICE_ID_FORMAT", Error::driver_error);
		}

		if ((NU54DK.boardModel() == nullptr) || (NU54DK.boardTarget() == nullptr) ||
			(NU54DK.socName() == nullptr))
		{
			fail("IDENTITY_NULL", Error::driver_error);
		}
		Serial.print("NUCODE_M15_AUTO_IDENTITY:PASS:model=");
		Serial.print(NU54DK.boardModel());
		Serial.print(":target=");
		Serial.print(NU54DK.boardTarget());
		Serial.print(":soc=");
		Serial.print(NU54DK.socName());
		Serial.print(":device_id=");
		Serial.println(device_id);

		if ((boot_reset_report.cause & ~boot_reset_report.supported) != 0U)
		{
			fail("RESET_MASK", Error::driver_error);
		}
		Serial.print("NUCODE_M15_AUTO_RESET:PASS:phase=initial:cause=");
		Serial.print(static_cast<unsigned long>(boot_reset_report.cause));
		Serial.print(":supported=");
		Serial.println(static_cast<unsigned long>(boot_reset_report.supported));

		const std::uint64_t before = NU54DK.uptimeMilliseconds();
		k_sleep(K_MSEC(25));
		const std::uint64_t after = NU54DK.uptimeMilliseconds();
		if ((after <= before) || ((after - before) < 20ULL))
		{
			fail("UPTIME_64", Error::driver_error);
		}
		Serial.print("NUCODE_M15_AUTO_UPTIME:PASS:before=");
		Serial.print(static_cast<unsigned long long>(before));
		Serial.print(":after=");
		Serial.println(static_cast<unsigned long long>(after));
	}

	/** @brief GRTC 64-bit counter와 work queue alarm callback을 검증합니다. */
	void testGrtcAlarm(void)
	{
		const std::uint64_t before = NU54DK.hardwareCounterTicks();
		atomic_set(&alarm_callback_count, 0);
		requireSuccess(
			NU54DK.alarmAfterMicroseconds(alarm_delay_us, alarmCallback, nullptr),
			"GRTC_ARM");
		if (!NU54DK.alarmPending())
		{
			fail("GRTC_PENDING", Error::driver_error);
		}
		if (k_sem_take(&alarm_completed, K_SECONDS(2)) != 0)
		{
			fail("GRTC_TIMEOUT", Error::driver_error);
		}
		const std::uint64_t after = NU54DK.hardwareCounterTicks();
		if ((atomic_get(&alarm_callback_count) != 1) || (after <= before) ||
			NU54DK.alarmPending() || (NU54DK.hardwareCounterFrequency() == 0U))
		{
			fail("GRTC_RESULT", Error::driver_error);
		}
		Serial.print("NUCODE_M15_AUTO_GRTC:PASS:frequency=");
		Serial.print(static_cast<unsigned long>(NU54DK.hardwareCounterFrequency()));
		Serial.print(":before=");
		Serial.print(static_cast<unsigned long long>(before));
		Serial.print(":scheduled=");
		Serial.print(static_cast<unsigned long long>(alarm_scheduled_ticks));
		Serial.print(":after=");
		Serial.print(static_cast<unsigned long long>(after));
		Serial.println(":callbacks=1");
	}

	/** @brief settings payload를 저장하고 다음 software reset 단계를 기록합니다. */
	void beginSettingsReset(ScenarioState &state)
	{
		requireSuccess(
			NU54DK.storagePut(payload_key, expected_payload, sizeof(expected_payload)),
			"SETTINGS_SAVE");
		saveState(state, Stage::soft_reset);
		Serial.print("NUCODE_M15_AUTO_SETTINGS:SAVED:length=");
		Serial.println(static_cast<unsigned int>(sizeof(expected_payload)));
		Serial.println("NUCODE_M15_AUTO_TRANSITION:next=soft_reset:method=software");
		Serial.flush();
		requireSuccess(NU54DK.clearResetCause(), "RESET_CLEAR_INITIAL");
		sys_reboot(SYS_REBOOT_COLD);
		__builtin_unreachable();
	}

	/** @brief software reset 뒤 settings load/delete와 WDT stop 생존을 검증합니다. */
	void continueAfterSoftwareReset(ScenarioState &state)
	{
		requireResetCause(ResetCause::software, "software");
		std::uint8_t payload[sizeof(expected_payload)] = {};
		std::size_t actual_length = 0U;
		requireSuccess(
			NU54DK.storageGet(payload_key, payload, sizeof(payload), actual_length),
			"SETTINGS_LOAD");
		if ((actual_length != sizeof(expected_payload)) ||
			(::memcmp(payload, expected_payload, sizeof(payload)) != 0))
		{
			fail("SETTINGS_VALUE", Error::driver_error);
		}
		requireSuccess(NU54DK.storageRemove(payload_key), "SETTINGS_DELETE");
		actual_length = 0U;
		const Error deleted_result =
			NU54DK.storageGet(payload_key, payload, sizeof(payload), actual_length);
		if ((deleted_result != Error::not_found) || (actual_length != 0U))
		{
			fail("SETTINGS_DELETE_VERIFY", deleted_result);
		}
		Serial.println("NUCODE_M15_AUTO_SETTINGS:LOAD_DELETE:PASS:length=8");

		requireSuccess(NU54DK.watchdogBegin(watchdog_stop_timeout_ms), "WDT_STOP_BEGIN");
		for (std::uint32_t feed = 0U; feed < 3U; ++feed)
		{
			k_sleep(K_MSEC(400));
			requireSuccess(NU54DK.watchdogFeed(), "WDT_STOP_FEED");
		}
		requireSuccess(NU54DK.watchdogStop(), "WDT_STOP");
		if (NU54DK.watchdogRunning())
		{
			fail("WDT_STOP_STATE", Error::driver_error);
		}
		k_sleep(K_MSEC(2300));
		Serial.println("NUCODE_M15_AUTO_WDT:STOP:PASS:feeds=3:survival_ms=2300");

		saveState(state, Stage::watchdog_arm);
		Serial.println("NUCODE_M15_AUTO_TRANSITION:next=watchdog_arm:method=software");
		Serial.flush();
		requireSuccess(NU54DK.clearResetCause(), "RESET_CLEAR_WDT_ARM");
		sys_reboot(SYS_REBOOT_COLD);
		__builtin_unreachable();
	}

	/** @brief 별도 boot에서 watchdog을 feed한 뒤 의도적으로 만료시킵니다. */
	void armWatchdogExpiry(ScenarioState &state)
	{
		requireResetCause(ResetCause::software, "watchdog_arm_software");
		saveState(state, Stage::watchdog_wait);
		requireSuccess(NU54DK.clearResetCause(), "RESET_CLEAR_WDT_EXPIRY");
		requireSuccess(NU54DK.watchdogBegin(watchdog_expiry_timeout_ms), "WDT_EXPIRY_BEGIN");
		k_sleep(K_MSEC(300));
		requireSuccess(NU54DK.watchdogFeed(), "WDT_EXPIRY_FEED");
		Serial.println("NUCODE_M15_AUTO_WDT:EXPIRY_ARMED:timeout_ms=1500:feeds=1");
		Serial.flush();
		k_sleep(K_SECONDS(5));
		fail("WDT_DID_NOT_RESET", Error::driver_error);
	}

	/** @brief watchdog reset cause를 확인하고 timed System OFF를 시작합니다. */
	void beginTimedSystemOff(ScenarioState &state)
	{
		requireResetCause(ResetCause::watchdog, "watchdog");
		saveState(state, Stage::timed_wake_wait);
		Serial.println("NUCODE_M15_AUTO_SYSTEM_OFF:REQUESTED:duration_us=2000000");
		Serial.println("NUCODE_M15_AUTO_SYSTEM_OFF:ENTERING");
		Serial.flush();
		requireSuccess(
			NU54DK.enterSystemOffAfter(system_off_delay_us), "SYSTEM_OFF_ENTER");
		__builtin_unreachable();
	}

	/** @brief timed GRTC wake의 reset 원인과 settings 정리를 확인합니다. */
	[[noreturn]] void finishTimedWake(ScenarioState &state)
	{
		requireResetCause(ResetCause::clock, "timed_wake");
		requireSuccess(NU54DK.storageRemove(state_key), "STATE_DELETE_FINAL");
		Serial.print("NUCODE_M15_AUTO_SYSTEM_OFF:WAKE:PASS:duration_us=2000000:cause=");
		Serial.println(static_cast<unsigned long>(boot_reset_report.cause));
		Serial.print("NUCODE_M15_AUTO_FINAL:PASS:nonce=");
		Serial.println(state.nonce);
		Serial.flush();
		for (;;)
		{
			k_sleep(K_SECONDS(1));
		}
	}

	/** @brief state를 제거하고 안전한 idle boot로 돌아갑니다. */
	[[noreturn]] void clearScenario(void)
	{
		static_cast<void>(NU54DK.storageRemove(payload_key));
		static_cast<void>(NU54DK.storageRemove(state_key));
		Serial.println("NUCODE_M15_AUTO_CLEAR:PASS");
		Serial.flush();
		requireSuccess(NU54DK.clearResetCause(), "RESET_CLEAR_COMMAND");
		sys_reboot(SYS_REBOOT_COLD);
		__builtin_unreachable();
	}
}

/** @brief 호스트 명령에 따라 reset 경계를 포함한 M15 자동 HIL을 실행합니다. */
void setup(void)
{
	Serial.begin(115200U);
	requireSuccess(NU54DK.storageBegin(), "STORAGE_BEGIN");
	requireSuccess(NU54DK.resetReport(boot_reset_report), "RESET_REPORT");

	ScenarioState state = {};
	std::size_t state_length = 0U;
	const Error state_result =
		NU54DK.storageGet(state_key, &state, sizeof(state), state_length);
	const bool state_exists = state_result == Error::none;
	const bool state_is_valid =
		state_exists && (state_length == sizeof(state)) && validState(state);
	if ((state_result != Error::none) && (state_result != Error::not_found))
	{
		fail("STATE_LOAD", state_result);
	}

	Serial.print("NUCODE_M15_AUTO_BOOT:schema=1:stage=");
	Serial.print(state_is_valid ? stageName(state.stage) : (state_exists ? "corrupt" : "idle"));
	Serial.print(":cause=");
	Serial.print(static_cast<unsigned long>(boot_reset_report.cause));
	Serial.print(":supported=");
	Serial.print(static_cast<unsigned long>(boot_reset_report.supported));
	Serial.print(":uptime_ms=");
	Serial.println(static_cast<unsigned long long>(NU54DK.uptimeMilliseconds()));
	reportState(state_is_valid ? &state : nullptr, state_is_valid ? stageName(state.stage) :
		(state_exists ? "corrupt" : "idle"));

	char command[96] = {};
	if (!readCommand(command, sizeof(command)))
	{
		fail("COMMAND_TOO_LONG", Error::invalid_argument);
	}
	if (::strcmp(command, "NUCODE_M15_AUTO_COMMAND:CLEAR") == 0)
	{
		clearScenario();
	}

	if (!state_is_valid)
	{
		constexpr char start_prefix[] = "NUCODE_M15_AUTO_COMMAND:START:";
		if (::strncmp(command, start_prefix, sizeof(start_prefix) - 1U) != 0)
		{
			fail("START_COMMAND", Error::invalid_argument);
		}
		const char *nonce = command + sizeof(start_prefix) - 1U;
		if (!validNonce(nonce))
		{
			fail("START_NONCE", Error::invalid_argument);
		}
		::memcpy(state.nonce, nonce, nonce_length + 1U);
		Serial.print("NUCODE_M15_AUTO_START:PASS:nonce=");
		Serial.println(state.nonce);
		testIdentityAndTime();
		testGrtcAlarm();
		beginSettingsReset(state);
	}

	constexpr char continue_prefix[] = "NUCODE_M15_AUTO_COMMAND:CONTINUE:";
	if ((::strncmp(command, continue_prefix, sizeof(continue_prefix) - 1U) != 0) ||
		(::strcmp(command + sizeof(continue_prefix) - 1U, state.nonce) != 0))
	{
		fail("CONTINUE_COMMAND", Error::permission_denied);
	}
	Serial.print("NUCODE_M15_AUTO_CONTINUE:PASS:stage=");
	Serial.print(stageName(state.stage));
	Serial.print(":nonce=");
	Serial.println(state.nonce);

	switch (state.stage)
	{
	case Stage::soft_reset:
		continueAfterSoftwareReset(state);
		break;
	case Stage::watchdog_arm:
		armWatchdogExpiry(state);
		break;
	case Stage::watchdog_wait:
		beginTimedSystemOff(state);
		break;
	case Stage::timed_wake_wait:
		finishTimedWake(state);
		break;
	default:
		fail("STATE_DISPATCH", Error::invalid_argument);
	}
}

/** @brief 모든 시험은 setup의 명시적 상태 전이에서만 실행합니다. */
void loop(void)
{
	k_sleep(K_SECONDS(1));
}
