/**
 * @file main.cpp
 * @brief TWIM20/21/22로 BQ25186 MASK_ID를 read-only 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <nucode/SerialFabric.h>

#include <variant.h>

#include <zephyr/kernel.h>

#include <cstddef>
#include <cstdint>

// SWD-only diagnostics; never insert diagnostic bytes into the exact UART frame.
extern "C" {
volatile std::uint32_t m24_twim_stage = 0U;
volatile std::uint32_t m24_twim_result = 0U;
}

namespace {
using namespace nucode::arduino;

inline constexpr std::uint8_t instance = CONFIG_NUCODE_M24_TWIM_HIL_INSTANCE;
inline constexpr std::size_t packet_size = 32U;
inline constexpr std::uint8_t pmic_address = 0x6AU;
inline constexpr std::uint8_t mask_id_register = 0x0CU;
inline constexpr std::uint8_t expected_mask_id = 0x41U;

alignas(4) std::uint8_t serial_workspace[packet_size * 2U]{};
alignas(4) std::uint8_t twi_workspace[8]{};
std::uint8_t *const command_buffer = &serial_workspace[0];
std::uint8_t *const response_buffer = &serial_workspace[packet_size];

const SerialSignalPin result_pins[] = {
    {SerialSignal::txd, PIN_P0_00},
    {SerialSignal::rxd, PIN_P0_01},
};
const SerialSignalPin pmic_pins[] = {
    {SerialSignal::sda, PIN_P1_02},
    {SerialSignal::scl, PIN_P1_03},
};

[[noreturn]] void halt() {
  while (true)
    k_sleep(K_FOREVER);
}

void require(SerialFabricResult result, std::uint32_t stage) {
  m24_twim_stage = stage;
  m24_twim_result = static_cast<std::uint32_t>(result);
  if (result != SerialFabricResult::success)
    halt();
}

void waitForTx(UarteHandle &serial) {
  while (true) {
    UarteEvent event{};
    if (!serial.takeEvent(event)) {
      k_sleep(K_MSEC(1));
      continue;
    }
    if ((event.type == UarteEventType::tx_complete) &&
        (event.buffer == response_buffer) &&
        (event.transferred == packet_size)) {
      return;
    }
    if ((event.type == UarteEventType::error) ||
        (event.type == UarteEventType::tx_cancelled)) {
      halt();
    }
  }
}

void send(UarteHandle &serial) {
  if (serial.transmitAsync(response_buffer, packet_size) !=
      SerialFabricResult::success) {
    halt();
  }
  waitForTx(serial);
}

void fillReady() {
  for (std::size_t index = 0U; index < packet_size; ++index)
    response_buffer[index] =
        static_cast<std::uint8_t>(0xD0U ^ instance ^ index);
}

bool validCommand() {
  for (std::size_t index = 0U; index < packet_size; ++index) {
    if (command_buffer[index] !=
        static_cast<std::uint8_t>(0x5AU ^ instance ^ index)) {
      return false;
    }
  }
  return true;
}

void fillResult(SerialFabricResult result) {
  for (std::size_t index = 0U; index < packet_size; ++index)
    response_buffer[index] = 0U;
  response_buffer[0] = 'N';
  response_buffer[1] = 'U';
  response_buffer[2] = 'T';
  response_buffer[3] = 'W';
  response_buffer[4] = instance;
  response_buffer[5] = static_cast<std::uint8_t>(result);
  response_buffer[6] = pmic_address;
  response_buffer[7] = mask_id_register;
  response_buffer[8] = twi_workspace[1];
  response_buffer[9] = expected_mask_id;
  response_buffer[10] = (result == SerialFabricResult::success &&
                         twi_workspace[1] == expected_mask_id)
                            ? 1U
                            : 0U;
  std::uint8_t checksum = 0U;
  for (std::size_t index = 0U; index < packet_size - 1U; ++index)
    checksum ^= response_buffer[index];
  response_buffer[packet_size - 1U] = checksum;
}
} // namespace

int main() {
  if ((instance != 20U) && (instance != 21U) && (instance != 22U))
    halt();

  auto *const serial = serialFabric().uarte(30U);
  auto *const twim = serialFabric().twim(instance);
  if ((serial == nullptr) || (twim == nullptr) ||
      (serial->configure({115200U, UarteParity::none, false}) !=
       SerialFabricResult::success) ||
      (twim->configure({TwiFabricFrequency::fast}) !=
       SerialFabricResult::success)) {
    halt();
  }

  const SerialDmaWorkspace serial_dma{serial_workspace,
                                      sizeof(serial_workspace)};
  const SerialFabricConfiguration serial_configuration{
      SerialRouteClass::p0_flexible,
      SerialElectricalProfile::dap_uart_bridge,
      result_pins,
      2U,
      &serial_dma,
      1U,
  };
  const SerialDmaWorkspace twi_dma{twi_workspace, sizeof(twi_workspace)};
  const SerialFabricConfiguration twi_configuration{
      SerialRouteClass::p1_flexible,
      SerialElectricalProfile::pmic_read_only,
      pmic_pins,
      2U,
      &twi_dma,
      1U,
  };
  require(serial->stage(serial_configuration), 1U);
  require(twim->stage(twi_configuration), 2U);
  require(serial->activate(), 3U);
  require(twim->activate(), 4U);

  while (true) {
    fillReady();
    m24_twim_stage = 5U;
    send(*serial);
    m24_twim_stage = 6U;
    if (serial->receiveAsync(command_buffer, packet_size) !=
        SerialFabricResult::success) {
      halt();
    }
    bool received = false;
    while (!received) {
      UarteEvent event{};
      if (!serial->takeEvent(event)) {
        k_sleep(K_MSEC(1));
        continue;
      }
      if ((event.type == UarteEventType::rx_complete) &&
          (event.buffer == command_buffer) &&
          (event.transferred == packet_size)) {
        received = true;
      } else if (event.type == UarteEventType::error) {
        halt();
      }
    }
    if (!validCommand())
      continue;

    m24_twim_stage = 7U;
    twi_workspace[0] = mask_id_register;
    twi_workspace[1] = 0U;
    const auto result = twim->transfer(pmic_address, &twi_workspace[0], 1U,
                                       &twi_workspace[1], 1U, 100000U);
    fillResult(result);
    m24_twim_result = static_cast<std::uint32_t>(result);
    send(*serial);
    m24_twim_stage = 8U;
    // One physical measurement per flash; no adjacent next-READY frame.
    halt();
  }
}
