/**
 * @file EEPROM.cpp
 * @brief NU54DK Settings/ZMS 기반 EEPROM mirror를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <EEPROM.h>

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)

#include <errno.h>
#include <string.h>

#include <zephyr/kernel.h>
#include <zephyr/settings/settings.h>
#include <zephyr/sys/atomic.h>

namespace
{
	constexpr char settings_key[] = "arduino/eeprom";
	constexpr std::uint32_t record_magic = 0x45503534UL;
	constexpr std::uint16_t record_version = 1U;
	constexpr std::size_t record_header_size = 12U;

	/** @brief EEPROM singleton의 고정 RAM 상태입니다. */
	struct EEPROMState
	{
		std::uint8_t mirror[EEPROMClass::maximum_size]{};
		std::size_t length{0U};
		bool started{false};
		bool dirty{false};
	};

	K_MUTEX_DEFINE(eeprom_mutex);
	EEPROMState state{};
	atomic_t last_error_value = ATOMIC_INIT(static_cast<atomic_val_t>(EEPROMError::none));
	atomic_t last_driver_error_value = ATOMIC_INIT(0);

	/** @brief 작은 정수를 record의 little-endian byte 순서로 기록합니다. */
	template <typename T>
	void storeInteger(std::uint8_t *destination, T value) noexcept
	{
		for (std::size_t index = 0U; index < sizeof(T); ++index)
		{
			destination[index] = static_cast<std::uint8_t>(value >> (index * 8U));
		}
	}

	/** @brief record의 little-endian byte를 작은 정수로 복원합니다. */
	template <typename T>
	T loadInteger(const std::uint8_t *source) noexcept
	{
		T value = 0U;
		for (std::size_t index = 0U; index < sizeof(T); ++index)
		{
			value |= static_cast<T>(source[index]) << (index * 8U);
		}
		return value;
	}

	/** @brief EEPROM payload의 IEEE CRC-32를 계산합니다. */
	std::uint32_t crc32(const std::uint8_t *data, std::size_t length) noexcept
	{
		std::uint32_t crc = 0xffffffffUL;
		for (std::size_t index = 0U; index < length; ++index)
		{
			crc ^= data[index];
			for (std::uint8_t bit = 0U; bit < 8U; ++bit)
			{
				const std::uint32_t mask = 0U - (crc & 1U);
				crc = (crc >> 1U) ^ (0xedb88320UL & mask);
			}
		}
		return ~crc;
	}

	/** @brief 마지막 공개 오류와 원래 driver 오류를 함께 기록합니다. */
	EEPROMError recordError(EEPROMError error, int driver_error = 0) noexcept
	{
		atomic_set(&last_error_value, static_cast<atomic_val_t>(error));
		atomic_set(&last_driver_error_value, static_cast<atomic_val_t>(driver_error));
		return error;
	}

	/** @brief Settings/ZMS 오류를 공개 EEPROM 오류로 변환합니다. */
	EEPROMError recordDriverError(int result) noexcept
	{
		if (result == -ENOSPC || result == -ENOMEM)
		{
			return recordError(EEPROMError::no_space, result);
		}
		if (result == -EINVAL)
		{
			return recordError(EEPROMError::invalid_argument, result);
		}
		return recordError(EEPROMError::driver_error, result);
	}

	/** @brief blocking storage API를 thread 문맥으로 제한합니다. */
	bool isThreadContext() noexcept
	{
		if (k_is_in_isr())
		{
			recordError(EEPROMError::invalid_context, -EWOULDBLOCK);
			return false;
		}
		return true;
	}

	/** @brief 호출자가 mutex를 가진 상태에서 저장소 record를 검증해 엽니다. */
	bool beginLocked(std::size_t requested_size) noexcept
	{
		if (requested_size == 0U || requested_size > EEPROMClass::maximum_size)
		{
			recordError(EEPROMError::invalid_argument, -EINVAL);
			return false;
		}

		if (state.started)
		{
			if (state.length != requested_size)
			{
				if (requested_size > state.length)
				{
					memset(state.mirror + state.length, 0xff,
						   requested_size - state.length);
				}
				state.length = requested_size;
				state.dirty = true;
			}
			recordError(EEPROMError::none);
			return true;
		}

		const int initialized = settings_subsys_init();
		if (initialized != 0)
		{
			recordDriverError(initialized);
			return false;
		}

		const ssize_t stored_size = settings_get_val_len(settings_key);
		if (stored_size == -ENOENT)
		{
			memset(state.mirror, 0xff, requested_size);
			state.length = requested_size;
			state.started = true;
			state.dirty = false;
			recordError(EEPROMError::none);
			return true;
		}
		if (stored_size < 0)
		{
			recordDriverError(static_cast<int>(stored_size));
			return false;
		}
		if (stored_size < static_cast<ssize_t>(record_header_size + 1U) ||
			stored_size > static_cast<ssize_t>(record_header_size + EEPROMClass::maximum_size))
		{
			recordError(EEPROMError::corrupt, -EBADMSG);
			return false;
		}

		std::uint8_t record[record_header_size + EEPROMClass::maximum_size]{};
		const ssize_t loaded = settings_load_one(settings_key, record, sizeof(record));
		if (loaded < 0)
		{
			recordDriverError(static_cast<int>(loaded));
			return false;
		}
		const std::uint32_t magic = loadInteger<std::uint32_t>(&record[0]);
		const std::uint16_t version = loadInteger<std::uint16_t>(&record[4]);
		const std::uint16_t stored_length = loadInteger<std::uint16_t>(&record[6]);
		const std::uint32_t expected_crc = loadInteger<std::uint32_t>(&record[8]);
		if (loaded != static_cast<ssize_t>(record_header_size + stored_length) ||
			magic != record_magic || version != record_version || stored_length == 0U ||
			stored_length > EEPROMClass::maximum_size ||
			crc32(record + record_header_size, stored_length) != expected_crc)
		{
			recordError(EEPROMError::corrupt, -EBADMSG);
			return false;
		}

		const std::size_t copied = requested_size < stored_length ? requested_size : stored_length;
		memcpy(state.mirror, record + record_header_size, copied);
		if (requested_size > copied)
		{
			memset(state.mirror + copied, 0xff, requested_size - copied);
		}
		state.length = requested_size;
		state.started = true;
		state.dirty = requested_size != stored_length;
		recordError(EEPROMError::none);
		return true;
	}

	/** @brief 호출자가 mutex를 가진 상태에서 dirty mirror를 원자 record로 저장합니다. */
	bool commitLocked() noexcept
	{
		if (!state.started)
		{
			recordError(EEPROMError::not_started, -EACCES);
			return false;
		}
		if (!state.dirty)
		{
			recordError(EEPROMError::none);
			return true;
		}

		std::uint8_t record[record_header_size + EEPROMClass::maximum_size]{};
		storeInteger<std::uint32_t>(&record[0], record_magic);
		storeInteger<std::uint16_t>(&record[4], record_version);
		storeInteger<std::uint16_t>(&record[6], static_cast<std::uint16_t>(state.length));
		storeInteger<std::uint32_t>(&record[8], crc32(state.mirror, state.length));
		memcpy(record + record_header_size, state.mirror, state.length);
		const int result = settings_save_one(settings_key, record,
										 record_header_size + state.length);
		if (result != 0)
		{
			recordDriverError(result);
			return false;
		}
		state.dirty = false;
		recordError(EEPROMError::none);
		return true;
	}
}

EEPROMClass EEPROM;

EERef::EERef(EEPROMClass *owner, int index) noexcept : owner_(owner), index_(index) {}

EERef::operator std::uint8_t() const
{
	return owner_->read(index_);
}

EERef &EERef::operator=(std::uint8_t value)
{
	owner_->write(index_, value);
	return *this;
}

EERef &EERef::operator=(const EERef &other)
{
	return operator=(static_cast<std::uint8_t>(other));
}

EERef &EERef::operator++() { return operator=(static_cast<std::uint8_t>(*this) + 1U); }
EERef &EERef::operator--() { return operator=(static_cast<std::uint8_t>(*this) - 1U); }
EERef &EERef::operator|=(std::uint8_t value) { return operator=(static_cast<std::uint8_t>(*this) | value); }
EERef &EERef::operator&=(std::uint8_t value) { return operator=(static_cast<std::uint8_t>(*this) & value); }
EERef &EERef::operator^=(std::uint8_t value) { return operator=(static_cast<std::uint8_t>(*this) ^ value); }
EERef &EERef::operator<<=(std::uint8_t value) { return operator=(static_cast<std::uint8_t>(*this) << value); }
EERef &EERef::operator>>=(std::uint8_t value) { return operator=(static_cast<std::uint8_t>(*this) >> value); }
EERef &EERef::update(std::uint8_t value)
{
	owner_->update(index_, value);
	return *this;
}

EEPtr::EEPtr(EEPROMClass *owner, int index) noexcept : owner_(owner), index_(index) {}
EERef EEPtr::operator*() const { return EERef(owner_, index_); }
EEPtr &EEPtr::operator++() { ++index_; return *this; }
EEPtr EEPtr::operator++(int) { EEPtr previous = *this; ++index_; return previous; }
EEPtr &EEPtr::operator--() { --index_; return *this; }
bool EEPtr::operator==(const EEPtr &other) const noexcept { return owner_ == other.owner_ && index_ == other.index_; }
bool EEPtr::operator!=(const EEPtr &other) const noexcept { return !(*this == other); }

bool EEPROMClass::begin(std::size_t size)
{
	if (!isThreadContext())
	{
		return false;
	}
	static_cast<void>(k_mutex_lock(&eeprom_mutex, K_FOREVER));
	const bool result = beginLocked(size);
	static_cast<void>(k_mutex_unlock(&eeprom_mutex));
	return result;
}

std::uint8_t EEPROMClass::read(int address)
{
	std::uint8_t value = 0U;
	static_cast<void>(readBlock(address, &value, sizeof(value)));
	return value;
}

void EEPROMClass::write(int address, std::uint8_t value)
{
	static_cast<void>(writeBlock(address, &value, sizeof(value), false));
}

void EEPROMClass::update(int address, std::uint8_t value)
{
	static_cast<void>(writeBlock(address, &value, sizeof(value), true));
}

bool EEPROMClass::commit()
{
	if (!isThreadContext())
	{
		return false;
	}
	static_cast<void>(k_mutex_lock(&eeprom_mutex, K_FOREVER));
	const bool result = commitLocked();
	static_cast<void>(k_mutex_unlock(&eeprom_mutex));
	return result;
}

bool EEPROMClass::reset(std::size_t size)
{
	if (!isThreadContext() || size == 0U || size > maximum_size)
	{
		if (size == 0U || size > maximum_size)
		{
			recordError(EEPROMError::invalid_argument, -EINVAL);
		}
		return false;
	}
	static_cast<void>(k_mutex_lock(&eeprom_mutex, K_FOREVER));
	const int initialized = settings_subsys_init();
	if (initialized != 0)
	{
		recordDriverError(initialized);
		static_cast<void>(k_mutex_unlock(&eeprom_mutex));
		return false;
	}
	memset(state.mirror, 0xff, size);
	state.length = size;
	state.started = true;
	state.dirty = true;
	const bool result = commitLocked();
	static_cast<void>(k_mutex_unlock(&eeprom_mutex));
	return result;
}

int EEPROMClass::length() const noexcept
{
	return state.started ? static_cast<int>(state.length) : static_cast<int>(maximum_size);
}

EEPROMError EEPROMClass::lastError() const noexcept
{
	return static_cast<EEPROMError>(atomic_get(&last_error_value));
}

int EEPROMClass::lastDriverError() const noexcept
{
	return static_cast<int>(atomic_get(&last_driver_error_value));
}

EERef EEPROMClass::operator[](int address)
{
	return EERef(this, address);
}

EEPtr EEPROMClass::begin() noexcept { return EEPtr(this, 0); }
EEPtr EEPROMClass::end() noexcept { return EEPtr(this, length()); }

bool EEPROMClass::readBlock(int address, void *destination, std::size_t length)
{
	if (!isThreadContext())
	{
		return false;
	}
	if (destination == nullptr || length == 0U)
	{
		recordError(EEPROMError::invalid_argument, -EINVAL);
		return false;
	}
	static_cast<void>(k_mutex_lock(&eeprom_mutex, K_FOREVER));
	if (!state.started && !beginLocked(maximum_size))
	{
		static_cast<void>(k_mutex_unlock(&eeprom_mutex));
		return false;
	}
	if (address < 0 || static_cast<std::size_t>(address) > state.length ||
		length > state.length - static_cast<std::size_t>(address))
	{
		recordError(EEPROMError::out_of_bounds, -ERANGE);
		static_cast<void>(k_mutex_unlock(&eeprom_mutex));
		return false;
	}
	memcpy(destination, state.mirror + address, length);
	recordError(EEPROMError::none);
	static_cast<void>(k_mutex_unlock(&eeprom_mutex));
	return true;
}

bool EEPROMClass::writeBlock(int address, const void *source, std::size_t length,
							 bool update_only)
{
	if (!isThreadContext())
	{
		return false;
	}
	if (source == nullptr || length == 0U)
	{
		recordError(EEPROMError::invalid_argument, -EINVAL);
		return false;
	}
	static_cast<void>(k_mutex_lock(&eeprom_mutex, K_FOREVER));
	if (!state.started && !beginLocked(maximum_size))
	{
		static_cast<void>(k_mutex_unlock(&eeprom_mutex));
		return false;
	}
	if (address < 0 || static_cast<std::size_t>(address) > state.length ||
		length > state.length - static_cast<std::size_t>(address))
	{
		recordError(EEPROMError::out_of_bounds, -ERANGE);
		static_cast<void>(k_mutex_unlock(&eeprom_mutex));
		return false;
	}
	if (!update_only || memcmp(state.mirror + address, source, length) != 0)
	{
		if (memcmp(state.mirror + address, source, length) != 0)
		{
			memcpy(state.mirror + address, source, length);
			state.dirty = true;
		}
	}
	recordError(EEPROMError::none);
	static_cast<void>(k_mutex_unlock(&eeprom_mutex));
	return true;
}

#endif
