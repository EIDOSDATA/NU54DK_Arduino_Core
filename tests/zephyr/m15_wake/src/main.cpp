/**
 * @file main.cpp
 * @brief M15 timed GRTC System OFF와 SW0(P1.13) wake를 한 image에서 검증합니다.
 *
 * @note DAP 연결 제어용 2연 SW1에서 DISABLE_SWD만 차단한 뒤 호스트가
 *       `ARM_TIMED:<nonce>`를 전송해야 전원 상태를 변경합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <NUCODE_NU54DK.h>

#include <cstddef>
#include <cstdint>
#include <string.h>

namespace
{
	using nucode::nu54dk::Error;
	using nucode::nu54dk::ResetCause;
	using nucode::nu54dk::ResetReport;
	using nucode::nu54dk::WakeButton;

	/** @brief timed GRTC wake의 상대 지연입니다. */
	constexpr std::uint64_t timed_wake_delay_us = 2000000ULL;

	/** @brief System OFF 전에 마지막 UART frame을 확실히 비우는 대기 시간입니다. */
	constexpr unsigned long system_off_uart_drain_delay_ms = 50UL;

	/** @brief 호스트 nonce의 16진수 문자 수입니다. */
	constexpr std::size_t nonce_length = 32U;

	/** @brief 허용하는 UART 명령의 최대 길이입니다. */
	constexpr std::size_t command_capacity = 64U;

	/** @brief 사용자가 DAP 격리와 버튼 준비를 완료할 수 있는 명령 대기 시간입니다. */
	constexpr unsigned long command_timeout_ms = 600000UL;

	/** @brief 재부팅 경계를 실제 HIL 세션에 결합하는 settings key입니다. */
	constexpr char state_key[] = "m15.system-off-state";

	/** @brief settings 상태 레코드의 magic입니다. */
	constexpr std::uint32_t state_magic = 0x4D313532UL;

	/** @brief UART와 settings 상태 레코드의 schema입니다. */
	constexpr std::uint32_t state_schema = 2U;

	/** @brief System OFF 재부팅 경계의 영구 상태입니다. */
	enum class Phase : std::uint32_t
	{
		timed_armed = 1U,
		timed_passed = 2U,
		button_armed = 3U,
	};

	/** @brief 전원 재부팅 뒤에도 검증 세션과 단계를 보존합니다. */
	struct ScenarioState
	{
		std::uint32_t magic;
		std::uint32_t schema;
		Phase phase;
		char nonce[nonce_length + 1U];
	};

	/** @brief 오류와 이미 캡처한 driver 오류를 fail-closed protocol에 기록합니다. */
	void reportFailure(const char *stage, Error error, int driver_error)
	{
		Serial.print("NUCODE_M15_SYSTEM_OFF_FAIL:stage=");
		Serial.print(stage);
		Serial.print(":error=");
		Serial.print(static_cast<unsigned int>(error));
		Serial.print(":driver_error=");
		Serial.println(driver_error);
		Serial.flush();
	}

	/** @brief 현재 BoardSystem driver 오류와 함께 오류를 기록합니다. */
	void reportFailure(const char *stage, Error error)
	{
		reportFailure(stage, error, NU54DK.lastDriverError());
	}

	/** @brief 기대 reset 원인과 다른 재부팅을 raw 값으로 기록합니다. */
	void reportResetFailure(
		const char *stage,
		std::uint32_t expected,
		const ResetReport &report)
	{
		Serial.print("NUCODE_M15_SYSTEM_OFF_FAIL:stage=");
		Serial.print(stage);
		Serial.print(":expected=");
		Serial.print(static_cast<unsigned long>(expected));
		Serial.print(":actual=");
		Serial.print(static_cast<unsigned long>(report.cause));
		Serial.print(":supported=");
		Serial.println(static_cast<unsigned long>(report.supported));
		Serial.flush();
	}

	/** @brief 주어진 문자열이 정확한 소문자 32자리 16진수 nonce인지 검사합니다. */
	bool validNonce(const char *nonce)
	{
		if (nonce == nullptr)
		{
			return false;
		}
		for (std::size_t index = 0U; index < nonce_length; ++index)
		{
			const char value = nonce[index];
			if (!(((value >= '0') && (value <= '9')) ||
				  ((value >= 'a') && (value <= 'f'))))
			{
				return false;
			}
		}
		return nonce[nonce_length] == '\0';
	}

	/** @brief settings에서 읽은 상태 레코드가 지원 schema와 단계인지 검사합니다. */
	bool validState(const ScenarioState &state)
	{
		const bool valid_phase =
			(state.phase == Phase::timed_armed) ||
			(state.phase == Phase::timed_passed) ||
			(state.phase == Phase::button_armed);
		return (state.magic == state_magic) &&
			   (state.schema == state_schema) && valid_phase && validNonce(state.nonce);
	}

	/** @brief 현재 HIL 상태를 settings에서 정확한 크기로 읽습니다. */
	Error loadState(ScenarioState &state, bool &exists)
	{
		std::size_t actual_length = 0U;
		const Error error = NU54DK.storageGet(
			state_key, &state, sizeof(state), actual_length);
		if (error == Error::not_found)
		{
			exists = false;
			return Error::none;
		}
		if (error != Error::none)
		{
			return error;
		}
		exists = true;
		if ((actual_length != sizeof(state)) || !validState(state))
		{
			return Error::driver_error;
		}
		return Error::none;
	}

	/** @brief 현재 HIL 단계를 영구 settings에 기록합니다. */
	Error saveState(const ScenarioState &state)
	{
		return NU54DK.storagePut(state_key, &state, sizeof(state));
	}

	/** @brief 최종 성공 뒤 HIL 상태를 제거합니다. */
	Error removeState()
	{
		const Error error = NU54DK.storageRemove(state_key);
		return error == Error::not_found ? Error::none : error;
	}

	/** @brief terminal 실패 전에 영구 상태를 제거해 다음 실행을 복구 가능하게 합니다. */
	bool removeStateBeforeFailure()
	{
		const Error remove_error = removeState();
		if (remove_error != Error::none)
		{
			reportFailure("FAILURE_STATE_REMOVE", remove_error);
			return false;
		}
		return true;
	}

	/** @brief 원래 driver 오류를 보존하면서 영구 상태를 제거하고 실패를 기록합니다. */
	void abortPersistedState(const char *stage, Error error)
	{
		const int driver_error = NU54DK.lastDriverError();
		if (!removeStateBeforeFailure())
		{
			return;
		}
		reportFailure(stage, error, driver_error);
	}

	/** @brief 영구 상태를 제거한 뒤 reset 원인 불일치를 기록합니다. */
	void abortPersistedResetState(
		const char *stage,
		std::uint32_t expected,
		const ResetReport &report)
	{
		if (!removeStateBeforeFailure())
		{
			return;
		}
		reportResetFailure(stage, expected, report);
	}

	/** @brief newline으로 끝난 UART 명령 하나를 제한 시간 안에 읽습니다. */
	bool waitForCommand(char *command, std::size_t capacity)
	{
		if ((command == nullptr) || (capacity < 2U))
		{
			return false;
		}
		std::size_t length = 0U;
		const unsigned long started = millis();
		while ((millis() - started) < command_timeout_ms)
		{
			while (Serial.available() > 0)
			{
				const int value = Serial.read();
				if (value < 0)
				{
					break;
				}
				const char character = static_cast<char>(value);
				if (character == '\r')
				{
					continue;
				}
				if (character == '\n')
				{
					command[length] = '\0';
					return true;
				}
				if (length >= (capacity - 1U))
				{
					return false;
				}
				command[length++] = character;
			}
			delay(1UL);
		}
		return false;
	}

	/** @brief 고정 명령 prefix 뒤의 nonce를 검증하고 반환합니다. */
	const char *commandNonce(const char *command, const char *prefix)
	{
		const std::size_t prefix_length = ::strlen(prefix);
		if ((command == nullptr) ||
			(::strncmp(command, prefix, prefix_length) != 0))
		{
			return nullptr;
		}
		const char *nonce = command + prefix_length;
		return validNonce(nonce) ? nonce : nullptr;
	}

	/** @brief timed System OFF를 host nonce와 결합해 시작합니다. */
	void armTimedWake()
	{
		char command[command_capacity] = {};
		if (!waitForCommand(command, sizeof(command)))
		{
			reportFailure("TIMED_COMMAND_TIMEOUT", Error::invalid_argument);
			return;
		}
		const char *nonce = commandNonce(command, "ARM_TIMED:");
		if (nonce == nullptr)
		{
			reportFailure("TIMED_COMMAND", Error::invalid_argument);
			return;
		}

		ScenarioState state = {};
		state.magic = state_magic;
		state.schema = state_schema;
		state.phase = Phase::timed_armed;
		::memcpy(state.nonce, nonce, nonce_length + 1U);
		const Error state_error = saveState(state);
		if (state_error != Error::none)
		{
			abortPersistedState("TIMED_STATE_SAVE", state_error);
			return;
		}

		Serial.print(
			"NUCODE_M15_SYSTEM_OFF_REQUEST:schema=2:phase=TIMED:nonce=");
		Serial.print(state.nonce);
		Serial.println(":duration_us=2000000");
		Serial.print(
			"NUCODE_M15_SYSTEM_OFF_ENTERING:schema=2:phase=TIMED:nonce=");
		Serial.print(state.nonce);
		Serial.println(":mode=GRTC_WAKE");
		Serial.flush();
		delay(system_off_uart_drain_delay_ms);

		const Error clear_error = NU54DK.clearResetCause();
		if (clear_error != Error::none)
		{
			abortPersistedState("TIMED_RESET_CLEAR", clear_error);
			return;
		}
		const Error off_error = NU54DK.enterSystemOffAfter(timed_wake_delay_us);
		abortPersistedState("ENTER_SYSTEM_OFF_TIMED", off_error);
	}

	/** @brief timed wake 성공 뒤 같은 nonce로 SW0 System OFF를 준비합니다. */
	void armButtonWake(ScenarioState &state)
	{
		Serial.print(
			"NUCODE_M15_SYSTEM_OFF_READY:schema=2:phase=BUTTON:command=ARM_BUTTON:nonce=");
		Serial.print(state.nonce);
		Serial.println(":wake=SW0:gpio=P1.13:active=LOW");

		char command[command_capacity] = {};
		if (!waitForCommand(command, sizeof(command)))
		{
			abortPersistedState("BUTTON_COMMAND_TIMEOUT", Error::invalid_argument);
			return;
		}
		const char *nonce = commandNonce(command, "ARM_BUTTON:");
		if ((nonce == nullptr) || (::strcmp(nonce, state.nonce) != 0))
		{
			abortPersistedState("BUTTON_COMMAND", Error::permission_denied);
			return;
		}

		state.phase = Phase::button_armed;
		const Error state_error = saveState(state);
		if (state_error != Error::none)
		{
			abortPersistedState("BUTTON_STATE_SAVE", state_error);
			return;
		}

		Serial.print(
			"NUCODE_M15_SYSTEM_OFF_REQUEST:schema=2:phase=BUTTON:nonce=");
		Serial.print(state.nonce);
		Serial.println(":wake=SW0:gpio=P1.13:active=LOW");
		Serial.print(
			"NUCODE_M15_SYSTEM_OFF_ACTION:schema=2:phase=BUTTON:nonce=");
		Serial.print(state.nonce);
		Serial.println(":expected=PRESS_LOW:host_wait_ms=2000");
		Serial.print(
			"NUCODE_M15_SYSTEM_OFF_ENTERING:schema=2:phase=BUTTON:nonce=");
		Serial.print(state.nonce);
		Serial.println(":mode=GPIO_WAKE");
		Serial.flush();
		delay(system_off_uart_drain_delay_ms);

		const Error clear_error = NU54DK.clearResetCause();
		if (clear_error != Error::none)
		{
			abortPersistedState("BUTTON_RESET_CLEAR", clear_error);
			return;
		}
		const Error off_error = NU54DK.enterSystemOffOnButton(WakeButton::sw0);
		abortPersistedState("ENTER_SYSTEM_OFF_BUTTON", off_error);
	}

	/** @brief CLOCK 원인이 정확한 timed wake만 승인하고 버튼 단계로 전이합니다. */
	void continueAfterTimedWake(ScenarioState &state, const ResetReport &report)
	{
		const std::uint32_t expected = static_cast<std::uint32_t>(ResetCause::clock);
		if ((report.cause != expected) ||
			((report.supported & expected) != expected))
		{
			abortPersistedResetState("TIMED_RESET", expected, report);
			return;
		}

		state.phase = Phase::timed_passed;
		const Error state_error = saveState(state);
		if (state_error != Error::none)
		{
			abortPersistedState("TIMED_PASS_STATE_SAVE", state_error);
			return;
		}
		const Error clear_error = NU54DK.clearResetCause();
		if (clear_error != Error::none)
		{
			abortPersistedState("TIMED_WAKE_RESET_CLEAR", clear_error);
			return;
		}

		Serial.print(
			"NUCODE_M15_SYSTEM_OFF_BOOT:schema=2:phase=TIMED_WAKE:nonce=");
		Serial.print(state.nonce);
		Serial.print(":cause=");
		Serial.print(static_cast<unsigned long>(report.cause));
		Serial.print(":supported=");
		Serial.println(static_cast<unsigned long>(report.supported));
		Serial.print(
			"NUCODE_M15_SYSTEM_OFF_WAKE:PASS:phase=TIMED:nonce=");
		Serial.print(state.nonce);
		Serial.println(":source=GRTC:cause=2048");
		armButtonWake(state);
	}

	/** @brief LOW_POWER_WAKE 원인이 정확한 SW0 wake만 최종 승인합니다. */
	void finishAfterButtonWake(const ScenarioState &state, const ResetReport &report)
	{
		const std::uint32_t expected =
			static_cast<std::uint32_t>(ResetCause::low_power_wake);
		if ((report.cause != expected) ||
			((report.supported & expected) != expected))
		{
			abortPersistedResetState("BUTTON_RESET", expected, report);
			return;
		}
		const Error remove_error = removeState();
		if (remove_error != Error::none)
		{
			reportFailure("BUTTON_STATE_REMOVE", remove_error);
			return;
		}
		const Error clear_error = NU54DK.clearResetCause();
		if (clear_error != Error::none)
		{
			reportFailure("BUTTON_WAKE_RESET_CLEAR", clear_error);
			return;
		}

		Serial.print(
			"NUCODE_M15_SYSTEM_OFF_BOOT:schema=2:phase=BUTTON_WAKE:nonce=");
		Serial.print(state.nonce);
		Serial.print(":cause=");
		Serial.print(static_cast<unsigned long>(report.cause));
		Serial.print(":supported=");
		Serial.println(static_cast<unsigned long>(report.supported));
		Serial.print(
			"NUCODE_M15_SYSTEM_OFF_WAKE:PASS:phase=BUTTON:nonce=");
		Serial.print(state.nonce);
		Serial.println(":source=SW0:gpio=P1.13:active=LOW:cause=128");
		Serial.print("NUCODE_M15_SYSTEM_OFF_PASS:schema=2:nonce=");
		Serial.print(state.nonce);
		Serial.println(":timed=PASS:button=PASS");
		Serial.flush();
	}
}

/** @brief DAP SWD 격리 뒤 timed GRTC와 SW0 wake를 순서대로 검증합니다. */
void setup(void)
{
	Serial.begin(115200U);

	const Error storage_error = NU54DK.storageBegin();
	if (storage_error != Error::none)
	{
		reportFailure("STORAGE_BEGIN", storage_error);
		return;
	}

	ResetReport report = {};
	const Error report_error = NU54DK.resetReport(report);
	if (report_error != Error::none)
	{
		reportFailure("RESET_REPORT", report_error);
		return;
	}

	ScenarioState state = {};
	bool state_exists = false;
	const Error state_error = loadState(state, state_exists);
	if (state_error != Error::none)
	{
		abortPersistedState("STATE_LOAD", state_error);
		return;
	}

	if (!state_exists)
	{
		const Error clear_error = NU54DK.clearResetCause();
		if (clear_error != Error::none)
		{
			reportFailure("IDLE_RESET_CLEAR", clear_error);
			return;
		}
		Serial.println(
			"NUCODE_M15_SYSTEM_OFF_READY:schema=2:phase=TIMED:command=ARM_TIMED:duration_us=2000000");
		armTimedWake();
		return;
	}

	switch (state.phase)
	{
	case Phase::timed_armed:
		continueAfterTimedWake(state, report);
		break;
	case Phase::button_armed:
		finishAfterButtonWake(state, report);
		break;
	case Phase::timed_passed:
		abortPersistedState("UNEXPECTED_BUTTON_READY_REBOOT", Error::driver_error);
		break;
	default:
		abortPersistedState("STATE_PHASE", Error::driver_error);
		break;
	}
}

/** @brief 시험 완료 또는 실패 뒤 추가 전원 동작 없이 대기합니다. */
void loop(void)
{
	delay(1000UL);
}
