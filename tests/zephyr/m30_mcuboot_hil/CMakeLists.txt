# SPDX-License-Identifier: MIT

cmake_minimum_required(VERSION 3.20.0)

get_filename_component(NUCODE_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nucode_m30_mcuboot_hil)

# @brief HIL protocol을 exact source revision에 결합합니다.
execute_process(
  COMMAND git -c "safe.directory=${NUCODE_ROOT}" -C "${NUCODE_ROOT}" rev-parse HEAD
  RESULT_VARIABLE revision_result
  OUTPUT_VARIABLE M30_BOOT_CORE_REVISION
  ERROR_VARIABLE revision_error
  OUTPUT_STRIP_TRAILING_WHITESPACE
)
string(LENGTH "${M30_BOOT_CORE_REVISION}" revision_length)
if(NOT revision_result EQUAL 0 OR NOT revision_length EQUAL 40 OR
   NOT M30_BOOT_CORE_REVISION MATCHES "^[0-9a-f]+$")
  message(FATAL_ERROR "M30 boot Core revision query failed: ${revision_error}")
endif()

target_sources(app PRIVATE src/main.cpp)
target_compile_definitions(app PRIVATE
  M30_BOOT_CORE_REVISION="${M30_BOOT_CORE_REVISION}"
)
