cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nucode_arduino_runtime_smoke)

target_sources(app PRIVATE
  src/runtime_smoke.cpp
  src/serial_event_probe.cpp
)
