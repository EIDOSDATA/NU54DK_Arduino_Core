cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nucode_arduino_interrupt_button)

target_sources(app PRIVATE src/interrupt_button.cpp)
