# SPDX-License-Identifier: MIT

cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nucode_m7_core_api)

target_sources(app PRIVATE
  src/main.cpp
)

# M7 semantic test는 SPI emulator를 chosen으로 사용하므로 SPI00 제약만
# 별도 expected-fail build에서 검증하고 이 target에서는 예외를 허용합니다.
target_compile_definitions(nucode_arduino_core PRIVATE
  NUCODE_ARDUINO_SPI_TEST_ALLOW_NON_SPI00=1
)

target_include_directories(app PRIVATE
  "${CMAKE_CURRENT_LIST_DIR}/../../../libraries/SPI/src"
  "${CMAKE_CURRENT_LIST_DIR}/../../../libraries/Wire/src"
)
