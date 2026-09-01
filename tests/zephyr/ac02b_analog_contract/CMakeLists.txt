# SPDX-License-Identifier: MIT

cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nucode_ac02b_analog_contract)

target_sources(app PRIVATE
  src/main.cpp
  ../../../libraries/Servo/src/Servo.cpp
)

# AC-02B 전용 allocator는 부모 Core CMake 통합 전에도 이 계약 target에서
# wiring_analog.cpp와 같은 library에 정확히 한 번 연결합니다.
get_filename_component(AC02B_PWM_RUNTIME_SOURCE
  "${CMAKE_CURRENT_LIST_DIR}/../../../cores/arduino/internal/PwmRuntime.cpp"
  ABSOLUTE
)
get_target_property(AC02B_CORE_SOURCES nucode_arduino_core SOURCES)
list(FIND AC02B_CORE_SOURCES "${AC02B_PWM_RUNTIME_SOURCE}" AC02B_PWM_RUNTIME_INDEX)
if(AC02B_PWM_RUNTIME_INDEX EQUAL -1)
  target_sources(nucode_arduino_core PRIVATE
    "${AC02B_PWM_RUNTIME_SOURCE}"
  )
endif()

target_include_directories(app PRIVATE
  "${CMAKE_CURRENT_LIST_DIR}/../../../libraries/Servo/src"
)
