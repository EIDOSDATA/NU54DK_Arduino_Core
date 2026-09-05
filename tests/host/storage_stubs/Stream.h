/** @file @brief File 수명주기 시험용 Arduino Stream 인터페이스입니다. */
#pragma once
#include <cstddef>
#include <cstdint>
#include <string>
using String = std::string;
class Print
{
  public:
    virtual ~Print() = default;
    virtual std::size_t write(std::uint8_t) = 0;
    virtual std::size_t write(const std::uint8_t *, std::size_t) = 0;
};
class Stream : public Print
{
  public:
    virtual int available() = 0;
    virtual int read() = 0;
    virtual int peek() = 0;
    virtual void flush() = 0;
};
