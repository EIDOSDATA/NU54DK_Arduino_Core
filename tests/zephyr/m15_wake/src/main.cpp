/**
 * @file main.cpp
 * @brief M15 System OFF와 SW0(P1.13) wake를 명시적 UART ARM 뒤에 검증합니다.
 *
 * @note 이 image는 runner가 `ARM`을 보낼 때까지 전원 상태를 변경하지 않습니다.
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

	/** @brief 재부팅을 실제 HIL ARM과 결합하는 settings key입니다. */
	constexpr char armed_key[] = "m15.system-off-armed";

	/** @brief settings에 저장하는 고정 ARM 표식입니다. */
	constexpr std::uint32_t armed_magic = 0x4D313541UL;

	/** @brief 허용하는 단일 UART 명령의 최대 길이입니다. */
	constexpr std::size_t command_capacity = 8U;

	/** @brief ARM 명령을 기다리는 최대 시간입니다. */
	constexpr unsigned long command_timeout_ms = 60000UL;

	/** @brief 오류 열거값을 fail-closed protocol에 기록합니다. */
	void reportFailure(const char *stage, Error error)
	{
		Serial.print("NUCODE_M15_SYSTEM_OFF_FAIL:stage=");
		Serial.print(stage);
		Serial.print(":error=");
		Serial.print(static_cast<unsigned int>(error));
		Serial.print(":driver_error=");
		Serial.println(NU54DK.lastDriverError());
	}

	/** @brief reset report에 지정 원인 bit가 포함됐는지 반환합니다. */
	bool hasResetCause(const ResetReport &report, ResetCause cause)
	{
		return (report.cause & static_cast<std::uint32_t>(cause)) != 0U;
	}

	/** @brief settings의 ARM 표식이 정확히 존재하는지 확인합니다. */
	bool readArmedMarker(bool &armed)
	{
		std::uint32_t value = 0U;
		std::size_t actual_length = 0U;
		const Error error = NU54DK.storageGet(
			armed_key, &value, sizeof(value), actual_length);
		if (error == Error::not_found)
		{
			armed = false;
			return true;
		}
		if (error != Error::none)
		{
			reportFailure("STORAGE_GET", error);
			return false;
		}
		if ((actual_length != sizeof(value)) || (value != armed_magic))
		{
			reportFailure("STORAGE_MARKER", Error::driver_error);
			return false;
		}
		armed = true;
		return true;
	}

	/** @brief 이전 시험 표식을 제거하되 없는 key는 정상 상태로 취급합니다. */
	bool removeArmedMarker(const char *stage)
	{
		const Error error = NU54DK.storageRemove(armed_key);
		if ((error != Error::none) && (error != Error::not_found))
		{
			reportFailure(stage, error);
			return false;
		}
		return true;
	}

	/** @brief SW0 wake 재부팅이면 최종 PASS를 출력하고 true를 반환합니다. */
	bool reportWakeIfPresent(const ResetReport &report, bool armed)
	{
		if (!armed || !hasResetCause(report, ResetCause::low_power_wake))
		{
			return false;
		}
		if (!removeArmedMarker("STORAGE_REMOVE_WAKE"))
		{
			return true;
		}
		const Error clear_error = NU54DK.clearResetCause();
		if (clear_error != Error::none)
		{
			reportFailure("RESET_CLEAR_WAKE", clear_error);
			return true;
		}
		Serial.println(
			"NUCODE_M15_SYSTEM_OFF_BOOT:schema=1:phase=WAKE:reset=LOW_POWER_WAKE");
		Serial.println(
			"NUCODE_M15_SYSTEM_OFF_WAKE:PASS:source=SW0:gpio=P1.13:active=LOW");
		Serial.println("NUCODE_M15_SYSTEM_OFF_PASS");
		return true;
	}

	/** @brief newline으로 끝난 고정 크기 ARM 명령 하나를 제한 시간 안에 읽습니다. */
	bool waitForArmCommand()
	{
		char command[command_capacity] = {};
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
					return ::strcmp(command, "ARM") == 0;
				}
				if (length >= (command_capacity - 1U))
				{
					return false;
				}
				command[length++] = character;
			}
			delay(1UL);
		}
		return false;
	}

	/** @brief ARM 요청을 기록하고 원자적 SW0 System OFF 진입 API를 호출합니다. */
	void requestAndEnterSystemOff()
	{
		Serial.println(
			"NUCODE_M15_SYSTEM_OFF_REQUEST:command=ARM:wake=SW0:gpio=P1.13:active=LOW");
		const Error marker_error = NU54DK.storagePut(
			armed_key, &armed_magic, sizeof(armed_magic));
		if (marker_error != Error::none)
		{
			reportFailure("STORAGE_PUT", marker_error);
			return;
		}

		Serial.println(
			"NUCODE_M15_SYSTEM_OFF_ACTION:wake=SW0:expected=PRESS_LOW:host_wait_ms=2000");
		Serial.println("NUCODE_M15_SYSTEM_OFF_ENTERING:mode=BUTTON_WAKE");
		Serial.flush();

		const Error off_error = NU54DK.enterSystemOffOnButton(WakeButton::sw0);
		removeArmedMarker("STORAGE_REMOVE_OFF_FAIL");
		reportFailure("ENTER_SYSTEM_OFF_BUTTON", off_error);
	}
}

/** @brief 안전한 UART ARM gate를 거쳐 단 한 번 System OFF 시험을 수행합니다. */
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

	bool armed = false;
	if (!readArmedMarker(armed) || reportWakeIfPresent(report, armed))
	{
		return;
	}

	if (armed && !removeArmedMarker("STORAGE_REMOVE_STALE"))
	{
		return;
	}
	const Error clear_error = NU54DK.clearResetCause();
	if (clear_error != Error::none)
	{
		reportFailure("RESET_CLEAR_ARM", clear_error);
		return;
	}

	Serial.println(
		"NUCODE_M15_SYSTEM_OFF_READY:schema=1:command=ARM:wake=SW0:gpio=P1.13:active=LOW");
	if (!waitForArmCommand())
	{
		reportFailure("ARM_COMMAND", Error::invalid_argument);
		return;
	}
	requestAndEnterSystemOff();
}

/** @brief 시험 완료 또는 실패 뒤 추가 전원 동작 없이 대기합니다. */
void loop(void)
{
	delay(1000UL);
}
