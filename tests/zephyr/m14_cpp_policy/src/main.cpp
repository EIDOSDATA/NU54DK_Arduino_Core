/**
 * @file main.cpp
 * @brief M14의 C++ exception과 RTTI opt-in 정책을 QEMU에서 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <nucode/Diagnostics.h>

#include <zephyr/ztest.h>

#include <cmath>
#include <cstring>
#include <typeinfo>

#if !defined(CONFIG_CPP_EXCEPTIONS)
#error "M14 exception 정책 시험에는 CONFIG_CPP_EXCEPTIONS가 필요합니다."
#endif

#if !defined(CONFIG_CPP_RTTI)
#error "M14 RTTI 정책 시험에는 CONFIG_CPP_RTTI가 필요합니다."
#endif

namespace
{

	/** @brief throw 값과 catch 값의 동일성을 확인하기 위한 형식입니다. */
	struct ExceptionValue
	{
		int value;
	};

	/** @brief stack unwind 중 소멸자 실행을 기록합니다. */
	class UnwindObserver
	{
	public:
		/** @brief 소멸 횟수 저장소를 연결합니다. */
		explicit UnwindObserver(int &destruction_count) noexcept
			: destruction_count_(destruction_count)
		{
		}

		/** @brief stack unwind가 이 객체를 소멸했음을 기록합니다. */
		~UnwindObserver()
		{
			++destruction_count_;
		}

	private:
		int &destruction_count_;
	};

	/** @brief RTTI 시험에 사용하는 다형 기반 형식입니다. */
	class RttiBase
	{
	public:
		/** @brief 다형 형식의 안전한 소멸을 보장합니다. */
		virtual ~RttiBase() = default;
	};

	/** @brief RTTI downcast가 식별해야 하는 파생 형식입니다. */
	class RttiDerived final : public RttiBase
	{
	public:
		/** @brief 파생 객체 식별값입니다. */
		int value{54};
	};

	/**
	 * @brief 지역 객체가 있는 frame에서 예외를 던집니다.
	 *
	 * @param destruction_count stack unwind 소멸 횟수 저장소입니다.
	 */
	[[noreturn]] void throwFromObservedFrame(int &destruction_count)
	{
		UnwindObserver observer(destruction_count);
		static_cast<void>(observer);
		throw ExceptionValue{54};
	}

}

ZTEST(m14_cpp_policy, test_throw_catch_and_stack_unwind)
{
	int destruction_count = 0;
	int caught_value = 0;

	try
	{
		throwFromObservedFrame(destruction_count);
	}
	catch (const ExceptionValue &exception)
	{
		caught_value = exception.value;
	}

	zassert_equal(caught_value, 54, "예외 값이 catch 경계를 통과하지 못했습니다.");
	zassert_equal(destruction_count, 1, "stack unwind 중 지역 소멸자가 한 번 실행되지 않았습니다.");
}

ZTEST(m14_cpp_policy, test_dynamic_cast_and_typeid)
{
	RttiDerived derived;
	RttiBase *base = &derived;

	auto *cast_result = dynamic_cast<RttiDerived *>(base);
	zassert_not_null(cast_result, "유효한 RTTI downcast에 실패했습니다.");
	zassert_equal(cast_result->value, 54, "RTTI downcast 객체의 값이 다릅니다.");
	zassert_true(typeid(*base) == typeid(RttiDerived), "typeid가 실제 파생 형식을 식별하지 못했습니다.");
}

ZTEST(m14_cpp_policy, test_random_and_diagnostics_on_zephyr)
{
	long first_sequence[8] = {};
	randomSeed(0x12345678UL);
	for (auto &value : first_sequence)
	{
		value = random(-50L, 75L);
		zassert_true((value >= -50L) && (value < 75L),
					 "random이 요청한 반열린 범위를 벗어났습니다.");
	}

	randomSeed(0x12345678UL);
	for (const auto expected : first_sequence)
	{
		zassert_equal(random(-50L, 75L), expected, "같은 seed가 같은 random 수열을 만들지 못했습니다.");
	}

	const nucode::arduino::Diagnostic diagnostic{
		nucode::arduino::DiagnosticSubsystem::wire,
		nucode::arduino::DiagnosticCode::driver_error,
		-5,
		17U,
	};
	char buffer[80] = {};
	const auto required = nucode::arduino::formatDiagnostic(
		diagnostic, buffer, sizeof(buffer));
	zassert_equal(required, std::strlen("NU54:wire:driver-error:driver=-5:detail=17"),
				  "진단 포맷 필요 길이가 다릅니다.");
	zassert_equal(std::strcmp(buffer, "NU54:wire:driver-error:driver=-5:detail=17"), 0,
				  "Zephyr target 진단 포맷 결과가 다릅니다.");

	int absolute_argument = -7;
	zassert_equal(abs(absolute_argument++), 7, "Arduino abs 결과가 다릅니다.");
	zassert_equal(absolute_argument, -6, "Arduino C++ abs가 인수를 반복 평가했습니다.");
	zassert_equal(std::abs(-11), 11, "Arduino.h 뒤의 std::abs가 가려졌습니다.");
}

ZTEST_SUITE(m14_cpp_policy, nullptr, nullptr, nullptr, nullptr, nullptr);
