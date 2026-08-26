# SPDX-License-Identifier: MIT

cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nucode_m3_runtime_regression)

get_filename_component(NUCODE_CORE_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)

target_sources(app PRIVATE
  src/main.cpp
  src/test_variant.cpp
  ${NUCODE_CORE_ROOT}/cores/arduino/wiring_digital.cpp
  ${NUCODE_CORE_ROOT}/cores/arduino/wiring_time.cpp
  ${NUCODE_CORE_ROOT}/cores/arduino/internal/runtime_scheduler.cpp
  ${NUCODE_CORE_ROOT}/cores/arduino/internal/time_backend_nrf54.cpp
)

target_include_directories(app BEFORE PRIVATE
  ${CMAKE_CURRENT_LIST_DIR}/include
  ${NUCODE_CORE_ROOT}/cores/arduino
)

target_include_directories(app SYSTEM PRIVATE
  ${NUCODE_CORE_ROOT}/third_party/ArduinoCore-API
)

target_compile_definitions(app PRIVATE
  CONFIG_NUCODE_ARDUINO_LOOP_SLEEP_ONE_TICK=1
)
