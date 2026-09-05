/** @file @brief EEPROM의 공개 byte proxy와 mirror API facade입니다.
 * SPDX-License-Identifier: MIT
 */
#include <EEPROM.h>
#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include "internal/EEPROMInternal.h"
using namespace nucode::eeprom::internal;
EEPROMClass EEPROM;

EERef::EERef(EEPROMClass *owner, int index) noexcept : owner_(owner), index_(index)
{
}

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

EERef &EERef::operator++()
{
    return operator=(static_cast<std::uint8_t>(*this) + 1U);
}
EERef &EERef::operator--()
{
    return operator=(static_cast<std::uint8_t>(*this) - 1U);
}
EERef &EERef::operator|=(std::uint8_t value)
{
    return operator=(static_cast<std::uint8_t>(*this) | value);
}
EERef &EERef::operator&=(std::uint8_t value)
{
    return operator=(static_cast<std::uint8_t>(*this) & value);
}
EERef &EERef::operator^=(std::uint8_t value)
{
    return operator=(static_cast<std::uint8_t>(*this) ^ value);
}
EERef &EERef::operator<<=(std::uint8_t value)
{
    return operator=(static_cast<std::uint8_t>(*this) << value);
}
EERef &EERef::operator>>=(std::uint8_t value)
{
    return operator=(static_cast<std::uint8_t>(*this) >> value);
}
EERef &EERef::update(std::uint8_t value)
{
    owner_->update(index_, value);
    return *this;
}

EEPtr::EEPtr(EEPROMClass *owner, int index) noexcept : owner_(owner), index_(index)
{
}
EERef EEPtr::operator*() const
{
    return EERef(owner_, index_);
}
EEPtr &EEPtr::operator++()
{
    ++index_;
    return *this;
}
EEPtr EEPtr::operator++(int)
{
    EEPtr previous = *this;
    ++index_;
    return previous;
}
EEPtr &EEPtr::operator--()
{
    --index_;
    return *this;
}
bool EEPtr::operator==(const EEPtr &other) const noexcept
{
    return owner_ == other.owner_ && index_ == other.index_;
}
bool EEPtr::operator!=(const EEPtr &other) const noexcept
{
    return !(*this == other);
}

bool EEPROMClass::begin(std::size_t size)
{
    if (!isThreadContext())
    {
        return false;
    }
    static_cast<void>(k_mutex_lock(&eepromMutex(), K_FOREVER));
    const bool result = beginLocked(size);
    static_cast<void>(k_mutex_unlock(&eepromMutex()));
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
    static_cast<void>(k_mutex_lock(&eepromMutex(), K_FOREVER));
    const bool result = commitLocked();
    static_cast<void>(k_mutex_unlock(&eepromMutex()));
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
    static_cast<void>(k_mutex_lock(&eepromMutex(), K_FOREVER));
    const int initialized = initializeSettings();
    if (initialized != 0)
    {
        recordDriverError(initialized);
        static_cast<void>(k_mutex_unlock(&eepromMutex()));
        return false;
    }
    memset(eepromState().mirror, 0xff, size);
    eepromState().length = size;
    eepromState().started = true;
    eepromState().dirty = true;
    const bool result = commitLocked();
    static_cast<void>(k_mutex_unlock(&eepromMutex()));
    return result;
}

int EEPROMClass::length() const noexcept
{
    return eepromState().started ? static_cast<int>(eepromState().length)
                                 : static_cast<int>(maximum_size);
}

EEPROMError EEPROMClass::lastError() const noexcept
{
    return static_cast<EEPROMError>(atomic_get(&lastErrorStorage()));
}

int EEPROMClass::lastDriverError() const noexcept
{
    return static_cast<int>(atomic_get(&lastDriverErrorStorage()));
}

EERef EEPROMClass::operator[](int address)
{
    return EERef(this, address);
}

EEPtr EEPROMClass::begin() noexcept
{
    return EEPtr(this, 0);
}
EEPtr EEPROMClass::end() noexcept
{
    return EEPtr(this, length());
}

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
    static_cast<void>(k_mutex_lock(&eepromMutex(), K_FOREVER));
    if (!eepromState().started && !beginLocked(maximum_size))
    {
        static_cast<void>(k_mutex_unlock(&eepromMutex()));
        return false;
    }
    if (address < 0 || static_cast<std::size_t>(address) > eepromState().length ||
        length > eepromState().length - static_cast<std::size_t>(address))
    {
        recordError(EEPROMError::out_of_bounds, -ERANGE);
        static_cast<void>(k_mutex_unlock(&eepromMutex()));
        return false;
    }
    memcpy(destination, eepromState().mirror + address, length);
    recordError(EEPROMError::none);
    static_cast<void>(k_mutex_unlock(&eepromMutex()));
    return true;
}

bool EEPROMClass::writeBlock(int address, const void *source, std::size_t length, bool update_only)
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
    static_cast<void>(k_mutex_lock(&eepromMutex(), K_FOREVER));
    if (!eepromState().started && !beginLocked(maximum_size))
    {
        static_cast<void>(k_mutex_unlock(&eepromMutex()));
        return false;
    }
    if (address < 0 || static_cast<std::size_t>(address) > eepromState().length ||
        length > eepromState().length - static_cast<std::size_t>(address))
    {
        recordError(EEPROMError::out_of_bounds, -ERANGE);
        static_cast<void>(k_mutex_unlock(&eepromMutex()));
        return false;
    }
    if (!update_only || memcmp(eepromState().mirror + address, source, length) != 0)
    {
        if (memcmp(eepromState().mirror + address, source, length) != 0)
        {
            memcpy(eepromState().mirror + address, source, length);
            eepromState().dirty = true;
        }
    }
    recordError(EEPROMError::none);
    static_cast<void>(k_mutex_unlock(&eepromMutex()));
    return true;
}

#endif
