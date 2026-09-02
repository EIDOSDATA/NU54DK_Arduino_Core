/**
 * @file EEPROM.h
 * @brief CRC로 보호되는 NU54DK Arduino EEPROM 호환 API입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_LIBRARY_EEPROM_H_
#define NUCODE_ARDUINO_LIBRARY_EEPROM_H_

#include <cstddef>
#include <cstdint>

class EEPROMClass;

/** @brief EEPROM API의 안정된 오류 분류입니다. */
enum class EEPROMError : std::uint8_t
{
	none = 0U,
	invalid_argument,
	invalid_context,
	not_started,
	out_of_bounds,
	corrupt,
	no_space,
	driver_error,
};

/** @brief 한 EEPROM byte를 읽고 갱신하는 Arduino 호환 proxy입니다. */
class EERef
{
public:
	/** @brief proxy가 가리키는 byte를 읽습니다. */
	operator std::uint8_t() const;

	/** @brief proxy가 가리키는 byte를 RAM mirror에 씁니다. */
	EERef &operator=(std::uint8_t value);

	/** @brief 다른 proxy의 값을 RAM mirror에 복사합니다. */
	EERef &operator=(const EERef &other);

	/** @brief byte를 증가시킵니다. */
	EERef &operator++();

	/** @brief byte를 감소시킵니다. */
	EERef &operator--();

	/** @brief OR 연산 결과를 기록합니다. */
	EERef &operator|=(std::uint8_t value);

	/** @brief AND 연산 결과를 기록합니다. */
	EERef &operator&=(std::uint8_t value);

	/** @brief XOR 연산 결과를 기록합니다. */
	EERef &operator^=(std::uint8_t value);

	/** @brief shift-left 연산 결과를 기록합니다. */
	EERef &operator<<=(std::uint8_t value);

	/** @brief shift-right 연산 결과를 기록합니다. */
	EERef &operator>>=(std::uint8_t value);

	/** @brief 현재 byte와 같은 값이면 flash 쓰기 없이 유지합니다. */
	EERef &update(std::uint8_t value);

private:
	friend class EEPROMClass;
	friend class EEPtr;

	/** @brief EEPROM 객체와 byte 위치로 proxy를 만듭니다. */
	EERef(EEPROMClass *owner, int index) noexcept;

	EEPROMClass *owner_;
	int index_;
};

/** @brief EEPROM 범위를 순회하는 Arduino 호환 iterator입니다. */
class EEPtr
{
public:
	/** @brief 현재 위치의 byte proxy를 반환합니다. */
	EERef operator*() const;

	/** @brief 다음 byte로 이동합니다. */
	EEPtr &operator++();

	/** @brief 다음 byte로 이동하기 전 iterator를 반환합니다. */
	EEPtr operator++(int);

	/** @brief 이전 byte로 이동합니다. */
	EEPtr &operator--();

	/** @brief 두 iterator의 위치가 같은지 반환합니다. */
	bool operator==(const EEPtr &other) const noexcept;

	/** @brief 두 iterator의 위치가 다른지 반환합니다. */
	bool operator!=(const EEPtr &other) const noexcept;

private:
	friend class EEPROMClass;

	/** @brief EEPROM 객체와 순회 위치로 iterator를 만듭니다. */
	EEPtr(EEPROMClass *owner, int index) noexcept;

	EEPROMClass *owner_;
	int index_;
};

/**
 * @brief 1024-byte 고정 RAM mirror와 명시적 commit을 제공하는 EEPROM입니다.
 *
 * @details `write`, `update`, `put`은 RAM만 바꿉니다. 영구 저장은
 * `commit()`을 성공적으로 호출한 경우에만 일어납니다.
 */
class EEPROMClass
{
public:
	/** @brief 공개 EEPROM mirror의 최대 크기입니다. */
	static constexpr std::size_t maximum_size = 1024U;

	/** @brief 저장된 mirror를 검증해 요청 크기로 엽니다. */
	bool begin(std::size_t size);

	/** @brief RAM mirror의 한 byte를 읽습니다. */
	std::uint8_t read(int address);

	/** @brief RAM mirror의 한 byte를 쓰고 dirty 상태로 만듭니다. */
	void write(int address, std::uint8_t value);

	/** @brief 값이 다를 때만 RAM mirror를 갱신합니다. */
	void update(int address, std::uint8_t value);

	/** @brief dirty RAM mirror 전체를 CRC/version record 하나로 저장합니다. */
	bool commit();

	/** @brief 손상된 record를 포함해 mirror를 0xFF로 명시적으로 초기화합니다. */
	bool reset(std::size_t size = maximum_size);

	/** @brief 현재 열린 mirror 크기를 반환합니다. */
	int length() const noexcept;

	/** @brief 마지막 안정 오류를 반환합니다. */
	EEPROMError lastError() const noexcept;

	/** @brief 마지막 Zephyr driver 오류 번호를 반환합니다. */
	int lastDriverError() const noexcept;

	/** @brief 지정 주소의 byte proxy를 반환합니다. */
	EERef operator[](int address);

	/** @brief 첫 byte를 가리키는 iterator를 반환합니다. */
	EEPtr begin() noexcept;

	/** @brief mirror 끝을 가리키는 iterator를 반환합니다. */
	EEPtr end() noexcept;

	/** @brief trivially-copyable 값의 byte 표현을 RAM mirror에서 읽습니다. */
	template <typename T>
	T &get(int address, T &value)
	{
		static_assert(__is_trivially_copyable(T),
					  "EEPROM.get은 trivially-copyable 형식만 지원합니다.");
		static_cast<void>(readBlock(address, &value, sizeof(T)));
		return value;
	}

	/** @brief trivially-copyable 값의 byte 표현을 RAM mirror에 씁니다. */
	template <typename T>
	const T &put(int address, const T &value)
	{
		static_assert(__is_trivially_copyable(T),
					  "EEPROM.put은 trivially-copyable 형식만 지원합니다.");
		static_cast<void>(writeBlock(address, &value, sizeof(T), true));
		return value;
	}

private:
	friend class EERef;

	/** @brief 범위를 한 번 검증하고 byte 묶음을 읽습니다. */
	bool readBlock(int address, void *destination, std::size_t length);

	/** @brief 범위를 한 번 검증하고 byte 묶음을 씁니다. */
	bool writeBlock(int address, const void *source, std::size_t length,
					bool update_only);
};

/** @brief sketch가 공유하는 전역 EEPROM 객체입니다. */
extern EEPROMClass EEPROM;

#endif
