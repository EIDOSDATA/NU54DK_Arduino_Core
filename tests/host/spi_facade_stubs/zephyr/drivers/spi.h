/** @file @brief 고정 SDK의 SPI operation 비트와 전송 경계를 제공합니다. */
#pragma once
#include <zephyr/device.h>
#include <cstddef>
#include <cstdint>
using spi_operation_t = std::uint16_t;
#define SPI_OP_MODE_MASTER 0U
#define SPI_MODE_CPOL (1U << 1U)
#define SPI_MODE_CPHA (1U << 2U)
#define SPI_TRANSFER_MSB 0U
#define SPI_TRANSFER_LSB (1U << 4U)
#define SPI_WORD_SET(size) ((size) << 5U)
struct spi_config
{
    std::uint32_t frequency;
    spi_operation_t operation;
    std::uint16_t slave;
    std::uintptr_t cs;
    std::uint32_t word_delay;
};
struct spi_buf
{
    void *buf;
    std::size_t len;
};
struct spi_buf_set
{
    spi_buf *buffers;
    std::size_t count;
};
int spi_transceive(const device *, const spi_config *, const spi_buf_set *, const spi_buf_set *);
